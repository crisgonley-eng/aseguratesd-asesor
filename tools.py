# tools.py
import os

import requests

import db


def _notificar_whatsapp(nombre: str, telefono: str, ramo: str, detalles: str) -> dict:
    """Envía la notificación del lead al WhatsApp del asesor (si hay credenciales).

    No revienta si faltan credenciales: solo devuelve un estado informativo.
    """
    token = os.getenv("WHATSAPP_TOKEN", "").strip()
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "").strip()
    to = os.getenv("WHATSAPP_TO", "573004880299").strip()
    version = os.getenv("WHATSAPP_API_VERSION", "v21.0").strip()

    if not token or not phone_number_id:
        return {"enviado": False, "motivo": "sin_credenciales"}

    cuerpo = (
        f"✅ *Nuevo lead — Asegúrate SD*\n"
        f"👤 {nombre}\n"
        f"📱 {telefono}\n"
        f"🛡 {ramo}\n"
        f"📝 {detalles}"
    )
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    try:
        resp = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": cuerpo},
            },
            timeout=15,
        )
        ok = resp.status_code == 200
        if not ok:
            print(f"[WhatsApp] error {resp.status_code}: {resp.text[:300]}")
        return {"enviado": ok, "status_http": resp.status_code}
    except Exception as exc:  # pragma: no cover - fallos de red
        print(f"[WhatsApp] excepción: {exc}")
        return {"enviado": False, "error": str(exc)}


def registrar_lead_cotizacion(
    nombre_completo: str,
    telefono_whatsapp: str,
    ramo_interes: str,
    detalles_perfilamiento: str,
    correo_electronico: str = "",
) -> dict:
    """Registra un prospecto calificado para cotización en el CRM.

    Args:
        nombre_completo: Nombre completo del prospecto.
        telefono_whatsapp: Número de WhatsApp en formato internacional.
        ramo_interes: Ramo o tipo de seguro que le interesa.
        detalles_perfilamiento: Detalles del perfilamiento (tipo de
            establecimiento, tamaño, etc.).
        correo_electronico: Correo electrónico (opcional).

    Returns:
        dict con status y mensaje de confirmación.
    """
    origen = "Asesor Virtual Gemini - Asegúrate SD"

    # 1) Persistir el lead.
    lead_id = db.insertar_lead(
        nombre=nombre_completo,
        telefono=telefono_whatsapp,
        correo=correo_electronico,
        ramo=ramo_interes,
        detalles=detalles_perfilamiento,
        origen=origen,
    )
    print(
        f"[CRM LEAD REGISTRADO #{lead_id}]: "
        f"{nombre_completo} | {telefono_whatsapp} | {ramo_interes}"
    )

    # 2) Notificar al asesor por WhatsApp (si hay credenciales).
    notif = _notificar_whatsapp(
        nombre_completo, telefono_whatsapp, ramo_interes, detalles_perfilamiento
    )

    return {
        "status": "success",
        "mensaje": "Lead registrado correctamente. Un asesor contactará al cliente.",
        "lead_id": lead_id,
        "whatsapp_notificado": notif.get("enviado", False),
    }


def derivar_a_asesor_humano(motivo: str, resumen_caso: str) -> dict:
    """Transfiere la conversación a un asesor humano de Asegúrate SD.

    Args:
        motivo: Motivo de la derivación (p. ej. siniestro urgente o solicitud).
        resumen_caso: Resumen del caso hasta el momento.

    Returns:
        dict con status y mensaje de confirmación del handoff.
    """
    print(f"[HANDOFF HUMANO ACTIVADO]: Motivo: {motivo} | Resumen: {resumen_caso}")
    return {
        "status": "handoff_ready",
        "mensaje": "Conversación transferida a la cola humana de Asegúrate SD.",
    }
