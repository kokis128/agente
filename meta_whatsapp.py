"""
meta_whatsapp.py

Cliente mínimo para mandar mensajes de WhatsApp usando la API oficial y
gratuita de Meta (WhatsApp Cloud API). Ver README.md para los pasos de
configuración (crear la app en Meta for Developers, número de prueba, etc.).
"""

import os

import httpx

GRAPH_API_VERSION = "v21.0"


def _normalizar_numero_argentino(numero: str) -> str:
    """Los webhooks de Meta identifican a los celulares argentinos con un "9"
    extra después del "54" (ej. "5492604597817"), pero para ENVIAR un mensaje
    la Cloud API exige ese mismo número sin el "9" (ej. "542604597817"). Es una
    inconsistencia conocida de Meta específica de Argentina."""
    if numero.startswith("549") and len(numero) == 13:
        return "54" + numero[3:]
    return numero


async def enviar_mensaje_whatsapp(destinatario: str, texto: str) -> None:
    """Manda un mensaje de texto por WhatsApp al número `destinatario`
    (formato internacional sin "+", ej: "5491122334455")."""

    destinatario = _normalizar_numero_argentino(destinatario)

    token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    if not token or not phone_number_id:
        print(
            "[meta_whatsapp] Faltan WHATSAPP_ACCESS_TOKEN o WHATSAPP_PHONE_NUMBER_ID "
            "en el archivo .env, no se pudo enviar el mensaje."
        )
        return

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "messaging_product": "whatsapp",
        "to": destinatario,
        "type": "text",
        "text": {"body": texto},
    }

    from datetime import datetime, timezone

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
        _log(f"EXCEPCION al llamar a Graph API | to={destinatario} | {type(e).__name__}: {e}")
        print(f"[meta_whatsapp] Excepcion enviando mensaje: {type(e).__name__}: {e}")
        return

    _log(f"to={destinatario} | status={res.status_code} | body={res.text}")

    if res.status_code >= 300:
        print(f"[meta_whatsapp] Error enviando mensaje ({res.status_code}): {res.text}")
    else:
        print(f"[meta_whatsapp] Mensaje enviado OK a {destinatario} (status {res.status_code})")
