"""
instagram_meta.py

Cliente minimo para mandar respuestas por Instagram Direct usando la
Instagram Messaging API (Graph API de Meta, App vinculada a una pagina de
Facebook con cuenta de Instagram profesional -- la misma app que ya usan
para WhatsApp). Ver README.md para los pasos de configuracion.
"""

import os
from datetime import datetime, timezone

import httpx

from agent import guardar_json, INSTAGRAM_STATUS_PATH

GRAPH_API_VERSION = "v21.0"


def _guardar_estado(ok: bool, motivo: str = "") -> None:
    """Guarda en data/instagram_status.json si el ultimo envio real funciono
    o no, para que el panel del dueno (dashboard.html) pueda avisar apenas
    el token de Instagram se vence, igual que ya hace con WhatsApp."""
    guardar_json(
        INSTAGRAM_STATUS_PATH,
        {
            "ok": ok,
            "motivo": motivo,
            "fecha": datetime.now(timezone.utc).isoformat(),
        },
    )


async def enviar_mensaje_instagram(destinatario_igsid: str, texto: str) -> None:
    """Manda un mensaje de texto por Instagram Direct al `destinatario_igsid`
    (el ID de Instagram del usuario -- el "sender.id" que llega en el
    webhook, NO su @usuario)."""

    token = os.getenv("INSTAGRAM_ACCESS_TOKEN")

    if not token:
        mensaje = (
            "Falta INSTAGRAM_ACCESS_TOKEN en el archivo .env, no se pudo "
            "enviar el mensaje de Instagram."
        )
        print(f"[instagram_meta] {mensaje}")
        _guardar_estado(False, mensaje)
        return

    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/me/messages"
    headers = {"Authorization": f"Bearer {token}"}
    body = {
        "recipient": {"id": destinatario_igsid},
        "message": {"text": texto},
    }

    def _log(linea: str) -> None:
        try:
            with open("instagram_debug.log", "a", encoding="utf-8") as logf:
                logf.write(f"{datetime.now(timezone.utc).isoformat()} | {linea}\n")
        except Exception as e:
            print(f"[instagram_meta] No se pudo escribir el log de debug: {e}")

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.post(url, headers=headers, json=body)
    except Exception as e:
        motivo = f"No se pudo conectar con la API de Instagram ({type(e).__name__})"
        _log(f"EXCEPCION al llamar a Graph API | to={destinatario_igsid} | {type(e).__name__}: {e}")
        print(f"[instagram_meta] Excepcion enviando mensaje: {type(e).__name__}: {e}")
        _guardar_estado(False, motivo)
        return

    _log(f"to={destinatario_igsid} | status={res.status_code} | body={res.text}")

    if res.status_code >= 300:
        codigo_error = None
        try:
            codigo_error = res.json().get("error", {}).get("code")
        except Exception:
            pass

        if res.status_code == 401 or codigo_error == 190:
            motivo = (
                "El token de Instagram (INSTAGRAM_ACCESS_TOKEN) vencio o es invalido. "
                "Genera uno nuevo en Meta for Developers > tu app > Instagram > API Setup."
            )
        else:
            motivo = f"Meta devolvio un error {res.status_code}: {res.text[:200]}"

        print(f"[instagram_meta] Error enviando mensaje ({res.status_code}): {res.text}")
        _guardar_estado(False, motivo)
    else:
        print(f"[instagram_meta] Mensaje enviado OK a {destinatario_igsid} (status {res.status_code})")
        _guardar_estado(True)
