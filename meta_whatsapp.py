"""
meta_whatsapp.py

Cliente minimo para mandar mensajes de WhatsApp usando la API oficial y
gratuita de Meta (WhatsApp Cloud API). Ver README.md para los pasos de
configuracion (crear la app en Meta for Developers, numero de prueba, etc.).
"""

import os
from datetime import datetime, timezone

import httpx

from agent import guardar_json, WHATSAPP_STATUS_PATH

GRAPH_API_VERSION = "v21.0"


def _normalizar_numero_argentino(numero: str) -> str:
    """Los webhooks de Meta identifican a los celulares argentinos con un "9"
    extra despues del "54" (ej. "5492604597817"), pero para ENVIAR un mensaje
    la Cloud API exige ese mismo numero sin el "9" (ej. "542604597817"). Es una
    inconsistencia conocida de Meta especifica de Argentina."""
    if numero.startswith("549") and len(numero) == 13:
        return "54" + numero[3:]
    return numero


def _guardar_estado(ok: bool, motivo: str = "") -> None:
    """Guarda en data/whatsapp_status.json si el ultimo envio real funciono o
    no, para que el panel del dueno (dashboard.html) pueda avisar apenas el
    token de acceso se vence, en vez de que se note recien cuando un mensaje
    real no llega el dia de la expo."""
    guardar_json(
        WHATSAPP_STATUS_PATH,
        {
            "ok": ok,
            "motivo": motivo,
            "fecha": datetime.now(timezone.utc).isoformat(),
        },
    )


async def enviar_mensaje_whatsapp(destinatario: str, texto: str) -> None:
    """Manda un mensaje de texto por WhatsApp al numero `destinatario`
    (formato internacional sin "+", ej: "5491122334455")."""

    destinatario = _normalizar_numero_argentino(destinatario)

    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    if not token or not phone_number_id:
        mensaje = (
            "Faltan WHATSAPP_ACCESS_TOKEN o WHATSAPP_PHONE_NUMBER_ID en el archivo "
            ".env, no se pudo enviar el mensaje."
        )
        print(f"[meta_whatsapp] {mensaje}")
        _guardar_estado(False, mensaje)
        return

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "messaging_product": "whatsapp",
        "to": destinatario,
        "type": "text",
        "text": {"body": texto},
    }

    def _log(linea: str) -> None:
        try:
            with open("whatsapp_debug.log", "a", encoding="utf-8") as logf:
                logf.write(f"{datetime.now(timezone.utc).isoformat()} | {linea}\n")
        except Exception as e:
            print(f"[meta_whatsapp] No se pudo escribir el log de debug: {e}")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(url, headers=headers, json=body)
    except Exception as e:
        motivo = f"No se pudo conectar con la API de WhatsApp ({type(e).__name__})"
        _log(f"EXCEPCION al llamar a Graph API | to={destinatario} | {type(e).__name__}: {e}")
        print(f"[meta_whatsapp] Excepcion enviando mensaje: {type(e).__name__}: {e}")
        _guardar_estado(False, motivo)
        return

    _log(f"to={destinatario} | status={res.status_code} | body={res.text}")

    if res.status_code >= 300:
        codigo_error = None
        try:
            codigo_error = res.json().get("error", {}).get("code")
        except Exception:
            pass

        if res.status_code == 401 or codigo_error == 190:
            motivo = (
                "El token de WhatsApp (WHATSAPP_ACCESS_TOKEN) vencio o es invalido. "
                "Genera uno nuevo en Meta for Developers > tu app > WhatsApp > API Setup."
            )
        else:
            motivo = f"Meta devolvio un error {res.status_code}: {res.text[:200]}"

        print(f"[meta_whatsapp] Error enviando mensaje ({res.status_code}): {res.text}")
        _guardar_estado(False, motivo)
    else:
        print(f"[meta_whatsapp] Mensaje enviado OK a {destinatario} (status {res.status_code})")
        _guardar_estado(True)
