# harness.py
import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import registrar_lead_cotizacion, derivar_a_asesor_humano

load_dotenv()

MODELO = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

SYSTEM_PROMPT = """
ROL Y OBJETIVO
Eres Sofía, asistente virtual comercial de Asegúrate SD, en Colombia. Tu objetivo es brindar una experiencia de atención excelente, identificar necesidades, orientar sobre el portafolio, recopilar la información necesaria para cotizaciones y facilitar el contacto con un asesor cuando corresponda.

PORTAFOLIO
Orienta consultas sobre seguros de autos, motos, SOAT, vida, accidentes personales, hogar, arrendamiento, salud, asistencias médicas, viajes, mascotas, seguros estudiantiles, seguros empresariales, responsabilidad civil, ARL y servicios complementarios de seguridad social, salud ocupacional, contabilidad, finanzas, tributación y gestión humana.

Ofrece únicamente los productos y servicios que estén confirmados en el portafolio vigente de Asegúrate SD. Distingue entre seguros, asistencias y servicios profesionales.

PROTOCOLO DE ATENCIÓN
1. Saluda con amabilidad e identifica la necesidad del cliente.
2. Haz una pregunta breve para precisar qué producto o servicio busca.
3. Explica las alternativas pertinentes de forma sencilla.
4. Solicita únicamente los datos necesarios para esa cotización.
5. Resume la información proporcionada para verificar que sea correcta.
6. Explica el siguiente paso y, cuando corresponda, coordina el contacto con un asesor.
7. Si el cliente consulta por varios servicios, organízalos por prioridad y atiéndelos progresivamente.

REGLAS COMERCIALES
- No inventes precios, promociones, descuentos, coberturas ni tiempos de aprobación.
- No garantices la emisión de una póliza.
- No afirmes que una cobertura está incluida sin verificar sus condiciones.
- No solicites todos los datos de una vez.
- No pidas información sensible innecesaria.
- Si no conoces una respuesta, indícalo con transparencia y ofrece validarla con un asesor.
- No afirmes haber enviado una cotización, realizado una llamada o agendado una cita si la acción no se ha completado.
- Mantén un tono cercano, respetuoso, profesional y comercial, sin presionar al cliente.

HERRAMIENTAS DISPONIBLES (úsalas cuando corresponda):
1. En cuanto tengas el nombre, el teléfono y el ramo de interés, llama INMEDIATAMENTE a la función `registrar_lead_cotizacion` para dejar el lead registrado. No dejes pasar el lead.
2. Si el usuario reporta un siniestro urgente o pide hablar con un asesor humano, llama a la función `derivar_a_asesor_humano`.

CIERRE
Termina cada interacción con un siguiente paso claro: completar los datos de cotización, resolver una duda, recibir opciones disponibles o contactar a un asesor humano.
"""

TOOL_FUNCTIONS = {
    "registrar_lead_cotizacion": registrar_lead_cotizacion,
    "derivar_a_asesor_humano": derivar_a_asesor_humano,
}


def _cliente() -> genai.Client:
    return genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


def _generar(cliente, contents, config, intentos: int = 4):
    """Genera contenido reintentando ante 503 transitorios (alta demanda)."""
    ultimo_error = None
    for i in range(intentos):
        try:
            return cliente.models.generate_content(
                model=MODELO, contents=contents, config=config
            )
        except Exception as exc:  # noqa: BLE001
            ultimo_error = exc
            texto = str(exc)
            if ("503" in texto) or ("UNAVAILABLE" in texto) or ("high demand" in texto):
                time.sleep(2 + i * 3)
                continue
            raise
    raise ultimo_error


def post_guardrails_check(bot_response_text: str) -> str:
    """Valida que el modelo no prometa precios exactos alucinados."""
    patron_precio = r"(cuesta|vale|precio es de)\s*(\$|\d+)"
    if re.search(patron_precio, bot_response_text, re.IGNORECASE):
        bot_response_text += "\n\n*(Nota: Las tarifas finales varían según el perfil de riesgo y aseguradora. Uno de nuestros asesores te enviará el comparativo formal.)*"
    return bot_response_text


def procesar_mensaje_usuario(historial_mensajes: list, nuevo_mensaje: str) -> str:
    """
    historial_mensajes: lista de dicts [{'role': 'user'|'model', 'text': '...'}]
    """
    # Construir contenido para Gemini
    contents = []
    for m in historial_mensajes:
        role = "user" if m["role"] == "user" else "model"
        contents.append(
            types.Content(role=role, parts=[types.Part.from_text(text=m["text"])])
        )

    # Agregar el mensaje entrante
    contents.append(
        types.Content(role="user", parts=[types.Part.from_text(text=nuevo_mensaje)])
    )

    # Configuración con herramientas y system prompt
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.3,  # Baja temperatura para evitar alucinaciones
        tools=[registrar_lead_cotizacion, derivar_a_asesor_humano],
    )

    cliente = _cliente()

    # 1. Llamada al modelo
    response = _generar(cliente, contents, config)

    # 2. Manejo de Tool Calls (si el modelo decide ejecutar una acción)
    if response.function_calls:
        # Turno del modelo con las llamadas a herramientas (se añade una sola vez).
        contents.append(response.candidates[0].content)

        # Ejecutar todas las herramientas pedidas y armar sus respuestas.
        partes_respuesta = []
        for call in response.function_calls:
            func = TOOL_FUNCTIONS.get(call.name)
            if func:
                try:
                    resultado_tool = func(**dict(call.args or {}))
                except TypeError as exc:
                    resultado_tool = {
                        "status": "error",
                        "mensaje": f"Argumentos inválidos para {call.name}: {exc}",
                    }
            else:
                resultado_tool = {
                    "status": "error",
                    "mensaje": f"Herramienta desconocida: {call.name}",
                }
            partes_respuesta.append(
                types.Part.from_function_response(
                    name=call.name, response={"result": resultado_tool}
                )
            )

        contents.append(types.Content(role="user", parts=partes_respuesta))

        # Segunda llamada con la respuesta de la herramienta
        follow_up = _generar(cliente, contents, config)
        return post_guardrails_check(follow_up.text)

    # 3. Respuesta estándar con validación de Guardrails
    return post_guardrails_check(response.text)
