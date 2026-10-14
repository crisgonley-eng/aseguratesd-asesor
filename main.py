# main.py
import html
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

import db
from harness import procesar_mensaje_usuario

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

# Valores que consideramos "sin key real" para no llamar a la API con basura.
_PLACEHOLDERS = {"", "tu_api_key_aqui", "your_api_key_here", "tu_api_key", "xxx"}

ESTADOS = ["nuevo", "contactado", "cotizado", "cerrado"]


def _key_configurada() -> bool:
    return GEMINI_API_KEY.lower() not in _PLACEHOLDERS


app = FastAPI(title="Asegúrate SD - Agente Gemini")


class ChatRequest(BaseModel):
    session_id: str
    mensaje: str
    historial: list = []  # Lista de objetos {'role': 'user'|'model', 'text': '...'}


class EstadoUpdate(BaseModel):
    estado: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "gemini_configurado": _key_configurada()}


@app.post("/api/chat")
def chat_endpoint(request: ChatRequest):
    if not _key_configurada():
        return JSONResponse(
            status_code=503,
            content={
                "error": "GEMINI_API_KEY no configurada. Pon tu clave real en .env.",
            },
        )

    try:
        respuesta_agente = procesar_mensaje_usuario(request.historial, request.mensaje)
    except Exception as exc:  # pragma: no cover - fallos de red/API
        return JSONResponse(
            status_code=502,
            content={
                "error": f"Fallo al consultar Gemini: {type(exc).__name__}: {exc}",
            },
        )

    return {"session_id": request.session_id, "respuesta": respuesta_agente}


@app.get("/api/leads")
def listar_leads():
    return {"leads": db.listar_leads()}


@app.post("/api/leads/{lead_id}/estado")
def cambiar_estado(lead_id: int, body: EstadoUpdate):
    if body.estado not in ESTADOS:
        return JSONResponse(
            status_code=422,
            content={"error": f"Estado inválido. Usa uno de: {', '.join(ESTADOS)}"},
        )
    if not db.actualizar_estado(lead_id, body.estado):
        return JSONResponse(status_code=404, content={"error": "Lead no encontrado"})
    return {"ok": True, "lead_id": lead_id, "estado": body.estado}


@app.get("/admin", response_class=HTMLResponse)
def panel_admin():
    filas = "".join(_fila_lead(lead) for lead in db.listar_leads())
    tabla = (
        "<table><tr><th>ID</th><th>Fecha</th><th>Nombre</th><th>WhatsApp</th>"
        "<th>Ramo</th><th>Detalles</th><th>Estado</th></tr>"
        f"{filas}</table>"
        if filas
        else "<p class='vacio'>Aún no hay leads registrados.</p>"
    )
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leads — Asegúrate SD</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 2rem; color: #1f2937; }}
  h1 {{ font-size: 1.4rem; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
  th, td {{ border: 1px solid #e5e7eb; padding: .5rem .6rem; text-align: left; font-size: .9rem; vertical-align: top; }}
  th {{ background: #f3f4f6; }}
  select {{ font-size: .85rem; }}
  .vacio {{ color: #6b7280; }}
</style>
</head>
<body>
  <h1>Leads — Asegúrate SD</h1>
  {tabla}
  <script>
    async function cambiarEstado(id, estado) {{
      await fetch('/api/leads/' + id + '/estado', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ estado: estado }})
      }});
    }}
  </script>
</body>
</html>"""


def _fila_lead(lead: dict) -> str:
    opciones = "".join(
        f"<option value='{e}' {'selected' if e == lead['estado'] else ''}>{e}</option>"
        for e in ESTADOS
    )
    fecha = (lead.get("creado_en") or "")[:16].replace("T", " ")
    return (
        "<tr>"
        f"<td>{lead['id']}</td>"
        f"<td>{html.escape(fecha)}</td>"
        f"<td>{html.escape(lead['nombre'] or '')}</td>"
        f"<td>{html.escape(lead['telefono'] or '')}</td>"
        f"<td>{html.escape(lead['ramo'] or '')}</td>"
        f"<td>{html.escape(lead['detalles'] or '')}</td>"
        f"<td><select onchange='cambiarEstado({lead['id']}, this.value)'>{opciones}</select></td>"
        "</tr>"
    )


if __name__ == "__main__":
    import uvicorn

    puerto = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=puerto, reload=True)
