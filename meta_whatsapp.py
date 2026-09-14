"""
meta_whatsapp.py

Cliente mínimo para mandar mensajes de WhatsApp usando la API oficial y
gratuita de Meta (WhatsApp Cloud API). Ver README.md para los pasos de
configuración (crear la app en Meta for Developers, número de prueba, etc.).
"""

import os

import httpx

GRAPH_API_VERSION = "v21.0"


async def enviar_mensaje_whatsapp(destinatario: str, texto: str) -> None:
    """Manda un mensaje de texto por WhatsApp al número `destinatario`
    (formato internacional sin "+", ej: "5491122334455")."""

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

    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(url, headers=headers, json=body)

    if res.status_code >= 300:
        print(f"[meta_whatsapp] Error enviando mensaje ({res.status_code}): {res.text}")
