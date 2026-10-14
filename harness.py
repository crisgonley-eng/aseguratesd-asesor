# harness.py
import os
import re
import time

from dotenv import load_dotenv
from google import genai
from google.genai import types

from tools import registrar_lead_cotizacion, derivar_a_asesor_humano

load_dotenv()

MODELO = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite")

SYSTEM_PROMPT = """
Eres Sofía, la asesora virtual experta de Asegúrate SD. Tu propósito es perfilar clientes y guiarlos hacia una cotización formal.
- Tono: Empático, consultivo, profesional y conciso.
- Objetivo: Identificar la necesidad (autos, salud, vida, copropiedades, etc.), pedir máximo 1-2 datos a la vez, y agendar o capturar los datos de contacto.
- REGLAS DE NEGOCIO Y GUARDRAILS:
  1. NUNCA inventes primas o precios definitivos sin cotización oficial.
  2. Si el usuario reporta un siniestro urgente o pide un asesor humano, llama a la función `derivar_a_asesor_humano`.
  3. En cuanto tengas el nombre, el teléfono y el ramo de interés, llama INMEDIATAMENTE a `registrar_lead_cotizacion`, sin hacer preguntas adicionales. No dejes pasar el lead.
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
