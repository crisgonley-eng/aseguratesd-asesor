# main.py
import html
import json
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

    # Guardar el intercambio para poder supervisar las conversaciones.
    db.insertar_mensaje(request.session_id, "user", request.mensaje)
    db.insertar_mensaje(request.session_id, "model", respuesta_agente)

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


@app.get("/api/conversaciones")
def listar_conversaciones():
    return {"conversaciones": db.listar_conversaciones()}


@app.get("/api/conversaciones/{session_id}")
def ver_conversacion(session_id: str):
    return {"session_id": session_id, "mensajes": db.listar_mensajes(session_id)}


# ---------------------------------------------------------------------------
# Panel de supervisión
# ---------------------------------------------------------------------------
@app.get("/admin", response_class=HTMLResponse)
def panel_admin():
    leads = db.listar_leads()
    conversaciones = db.listar_conversaciones()

    total_leads = len(leads)
    leads_nuevos = sum(1 for l in leads if l["estado"] == "nuevo")
    total_conversaciones = len(conversaciones)

    filas_leads = "".join(_fila_lead(lead) for lead in leads)
    tarjetas_conv = "".join(_tarjeta_conversacion(c) for c in conversaciones)

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Panel — Asegúrate SD</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; margin: 0; background:#f3f4f6; color:#1f2937; }}
  header {{ background:#111827; color:#fff; padding: 1rem 2rem; }}
  header h1 {{ margin:0; font-size:1.3rem; }}
  header small {{ color:#9ca3af; }}
  .wrap {{ max-width: 1000px; margin: 1.5rem auto; padding: 0 1rem; }}
  .stats {{ display:flex; gap:1rem; margin-bottom:1.5rem; }}
  .card {{ background:#fff; border:1px solid #e5e7eb; border-radius:.6rem; padding:1rem; flex:1; }}
  .card .num {{ font-size:1.8rem; font-weight:700; }}
  .card .lbl {{ color:#6b7280; font-size:.85rem; }}
  section {{ background:#fff; border:1px solid #e5e7eb; border-radius:.6rem; padding:1rem 1.2rem; margin-bottom:1.5rem; }}
  h2 {{ font-size:1.05rem; margin:0 0 .8rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border:1px solid #e5e7eb; padding:.5rem .6rem; text-align:left; font-size:.87rem; vertical-align:top; }}
  th {{ background:#f9fafb; }}
  select {{ font-size:.85rem; }}
  .conv {{ border:1px solid #e5e7eb; border-radius:.5rem; padding:.8rem; margin-bottom:.7rem; }}
  .conv .meta {{ font-size:.8rem; color:#6b7280; margin-bottom:.4rem; }}
  .conv .prev {{ font-size:.9rem; color:#374151; }}
  .conv .mensajes {{ display:none; margin-top:.7rem; border-top:1px dashed #e5e7eb; padding-top:.7rem; }}
  .msg {{ margin-bottom:.6rem; font-size:.88rem; }}
  .msg.user {{ color:#111827; }}
  .msg.model {{ color:#0f766e; }}
  .msg .quien {{ font-weight:600; font-size:.75rem; text-transform:uppercase; letter-spacing:.03em; }}
  .btn {{ background:#2563eb; color:#fff; border:none; padding:.35rem .7rem; border-radius:.4rem; cursor:pointer; font-size:.82rem; }}
  .vacio {{ color:#6b7280; }}
</style>
</head>
<body>
<header>
  <h1>Panel de supervisión — Sofía</h1>
  <small>Asegúrate SD · Asesor Virtual</small>
</header>
<div class="wrap">

  <div class="stats">
    <div class="card"><div class="num">{total_leads}</div><div class="lbl">Leads totales</div></div>
    <div class="card"><div class="num">{leads_nuevos}</div><div class="lbl">Leads nuevos</div></div>
    <div class="card"><div class="num">{total_conversaciones}</div><div class="lbl">Conversaciones</div></div>
  </div>

  <section>
    <h2>Leads</h2>
    {("<table><tr><th>ID</th><th>Fecha</th><th>Nombre</th><th>WhatsApp</th><th>Ramo</th><th>Detalles</th><th>Estado</th></tr>" + filas_leads + "</table>") if filas_leads else "<p class='vacio'>Aún no hay leads.</p>"}
  </section>

  <section>
    <h2>Conversaciones</h2>
    {tarjetas_conv if tarjetas_conv else "<p class='vacio'>Aún no hay conversaciones.</p>"}
  </section>

</div>
<script>
  async function cambiarEstado(id, estado) {{
    await fetch('/api/leads/' + id + '/estado', {{
      method: 'POST',
      headers: {{ 'Content-Type': 'application/json' }},
      body: JSON.stringify({{ estado: estado }})
    }});
  }}

  async function verConversacion(sessionId, boton) {{
    const cont = document.getElementById('conv-' + sessionId);
    if (cont.style.display === 'block') {{
      cont.style.display = 'none';
      boton.textContent = 'Ver conversación';
      return;
    }}
    const resp = await fetch('/api/conversaciones/' + sessionId);
    const data = await resp.json();
    cont.innerHTML = data.mensajes.map(m =>
      `<div class="msg ${{m.role}}"><span class="quien">${{m.role === 'user' ? 'Cliente' : 'Sofía'}}</span><br>${{escapeHtml(m.text)}}</div>`
    ).join('');
    cont.style.display = 'block';
    boton.textContent = 'Ocultar';
  }}

  function escapeHtml(s) {{
    return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
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


def _tarjeta_conversacion(conv: dict) -> str:
    sid = conv["session_id"]
    fecha = (conv.get("ultimo") or "")[:16].replace("T", " ")
    return (
        "<div class='conv'>"
        f"<div class='meta'>🆔 {html.escape(sid)} · {conv['n_mensajes']} mensajes · {html.escape(fecha)}</div>"
        f"<div class='prev'>{html.escape(conv['preview'][:140] or '(sin mensajes)')}</div>"
        f"<div style='margin-top:.5rem'><button class='btn' onclick='verConversacion({html.escape(json.dumps(sid))}, this)'>Ver conversación</button></div>"
        f"<div class='mensajes' id='conv-{html.escape(sid)}'></div>"
        "</div>"
    )


if __name__ == "__main__":
    import uvicorn

    puerto = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=puerto, reload=True)
