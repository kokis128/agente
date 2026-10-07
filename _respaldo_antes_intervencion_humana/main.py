"""
main.py

Servidor FastAPI del agente. Expone:
- El WhatsApp simulado (public/whatsapp.html) e Instagram simulado
  (public/instagram.html) -> POST /api/chat
- El webhook real de WhatsApp vía Meta WhatsApp Cloud API -> /webhook/meta
- El webhook real de WhatsApp vía Twilio Sandbox (alternativa) -> POST /webhook/whatsapp
- El webhook real de Instagram Direct vía Meta -> /webhook/instagram
- El panel del dueño (public/dashboard.html) -> GET /api/logs, /api/pedidos
"""

import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import escape

from dotenv import load_dotenv

# Forzar resolución DNS solo por IPv4. Algunas conexiones de Windows/ISP
# tienen IPv6 mal configurado: los pedidos a dominios con registro AAAA
# (como graph.facebook.com) se cuelgan intentando conectar por IPv6 hasta
# hacer timeout, aunque el navegador (que sí hace fallback automático a
# IPv4) funcione perfecto. Este parche evita que httpx/asyncio intenten
# siquiera esa ruta.
_getaddrinfo_original = socket.getaddrinfo


def _getaddrinfo_solo_ipv4(host, port, family=0, type=0, proto=0, flags=0):
    resultados = _getaddrinfo_original(host, port, socket.AF_INET, type, proto, flags)
    return resultados


socket.getaddrinfo = _getaddrinfo_solo_ipv4

# Cargar .env ANTES de importar agent, para que las variables de entorno
# ya estén disponibles si algún módulo las necesita al importarse.
load_dotenv()

import io

import qrcode
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import (
    leer_json,
    guardar_json,
    responder_mensaje,
    actualizar_estado_pedido_excel,
    LOGS_PATH,
    PEDIDOS_PATH,
    PEDIDOS_XLSX_PATH,
    WHATSAPP_STATUS_PATH,
    INSTAGRAM_STATUS_PATH,
    NEGOCIO_PATH,
)
from meta_whatsapp import enviar_mensaje_whatsapp
from instagram_meta import enviar_mensaje_instagram

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"

app = FastAPI(title="Agente IA - Kiosco")


class MensajeChat(BaseModel):
    cliente: str
    mensaje: str
    canal: str = "whatsapp-simulado"  # o "instagram-simulado"


class EstadoPedido(BaseModel):
    estado: str  # "confirmado" | "rechazado"


@app.post("/api/chat")
async def chat(payload: MensajeChat):
    """Usado por el WhatsApp simulado y el Instagram simulado en el navegador."""
    resultado = await responder_mensaje(payload.cliente, payload.mensaje, payload.canal)
    return resultado


@app.get("/webhook/meta")
def verificar_webhook_meta(request: Request):
    """Meta llama a esta URL (GET) una sola vez, al configurar el webhook,
    para confirmar que el servidor es tuyo. Hay que responder con el mismo
    "hub.challenge" que mandan, siempre que el verify_token coincida con el
    que elegiste en WHATSAPP_VERIFY_TOKEN."""
    params = request.query_params
    modo = params.get("hub.mode")
    token_recibido = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    verify_token = os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    if modo == "subscribe" and verify_token and token_recibido == verify_token:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


@app.post("/webhook/meta")
async def webhook_meta(payload: dict):
    """Webhook real de WhatsApp vía Meta WhatsApp Cloud API (gratis).
    Configuración en https://developers.facebook.com/apps -> tu app ->
    WhatsApp -> Configuration -> Webhook. Ver README.md para el paso a paso."""
    try:
        cambios = payload["entry"][0]["changes"][0]["value"]
        mensajes = cambios.get("messages")
        if not mensajes:
            # Puede ser una notificación de "entregado"/"leído", no un mensaje nuevo.
            return {"status": "ignorado"}

        mensaje = mensajes[0]
        remitente = mensaje["from"]
        texto = mensaje.get("text", {}).get("body", "")

        resultado = await responder_mensaje(remitente, texto, "whatsapp-real-meta")
        await enviar_mensaje_whatsapp(remitente, resultado.respuesta)
    except Exception as err:  # noqa: BLE001 - no queremos que Meta reciba un 500
        print(f"Error en webhook de Meta: {err}")

    return {"status": "ok"}


@app.post("/webhook/whatsapp")
async def webhook_whatsapp(From: str = Form(...), Body: str = Form("")):
    """Webhook real de WhatsApp vía Twilio Sandbox (alternativa a Meta, ver README
    sobre por qué Twilio puede pedir tarjeta). Configurar esta URL (pública,
    ej. con ngrok) como "WHEN A MESSAGE COMES IN" en
    https://www.twilio.com/console/sms/whatsapp/sandbox
    """
    try:
        resultado = await responder_mensaje(From, Body, "whatsapp-real-twilio")
        respuesta_texto = resultado.respuesta
    except Exception as err:  # noqa: BLE001 - no queremos que Twilio reciba un 500
        respuesta_texto = "Hubo un problema, ya te contactamos."
        print(f"Error en webhook de WhatsApp: {err}")

    twiml = f'<?xml version="1.0" encoding="UTF-8"?><Response><Message>{escape(respuesta_texto)}</Message></Response>'
    return Response(content=twiml, media_type="text/xml")


@app.get("/webhook/instagram")
def verificar_webhook_instagram(request: Request):
    """Meta llama a esta URL (GET) al configurar el webhook de Instagram,
    igual que con WhatsApp. Si no configuraste INSTAGRAM_VERIFY_TOKEN por
    separado, se reutiliza WHATSAPP_VERIFY_TOKEN (misma app de Meta)."""
    params = request.query_params
    modo = params.get("hub.mode")
    token_recibido = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    verify_token = os.getenv("INSTAGRAM_VERIFY_TOKEN") or os.getenv("WHATSAPP_VERIFY_TOKEN", "")
    if modo == "subscribe" and verify_token and token_recibido == verify_token:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


@app.post("/webhook/instagram")
async def webhook_instagram(payload: dict):
    """Webhook real de Instagram Direct via Meta (misma app que WhatsApp,
    con el producto "Instagram" agregado). Configuracion en
    https://developers.facebook.com/apps -> tu app -> Instagram ->
    Webhooks. Ver README.md para el paso a paso."""
    try:
        entry = payload["entry"][0]
        eventos = entry.get("messaging", [])
        if not eventos:
            return {"status": "ignorado"}

        evento = eventos[0]
        mensaje = evento.get("message") or {}
        # "is_echo" son los mensajes que el propio negocio mando (si en algun
        # momento se suscribe tambien el campo message_echoes) -- ignorarlos
        # evita que el agente se responda a si mismo en bucle.
        if mensaje.get("is_echo") or not mensaje.get("text"):
            return {"status": "ignorado"}

        remitente = evento["sender"]["id"]
        texto = mensaje["text"]

        resultado = await responder_mensaje(remitente, texto, "instagram-real")
        await enviar_mensaje_instagram(remitente, resultado.respuesta)
    except Exception as err:  # noqa: BLE001 - no queremos que Meta reciba un 500
        print(f"Error en webhook de Instagram: {err}")

    return {"status": "ok"}


@app.get("/api/logs")
def obtener_logs():
    return leer_json(LOGS_PATH, [])


@app.get("/api/pedidos")
def obtener_pedidos():
    return leer_json(PEDIDOS_PATH, [])


@app.get("/api/whatsapp-status")
def whatsapp_status():
    """Estado del ultimo intento de envio por WhatsApp real (Meta Cloud API).
    Lo usa dashboard.html para avisar apenas el token de acceso se vence, en
    vez de que se note recien cuando un mensaje real no llega."""
    return leer_json(WHATSAPP_STATUS_PATH, {"ok": None, "motivo": "", "fecha": None})


@app.get("/api/instagram-status")
def instagram_status():
    """Igual que /api/whatsapp-status pero para Instagram Direct."""
    return leer_json(INSTAGRAM_STATUS_PATH, {"ok": None, "motivo": "", "fecha": None})


@app.get("/api/stats")
def stats():
    """Metricas para la fila de KPIs del panel del dueno."""
    logs = leer_json(LOGS_PATH, [])
    pedidos = leer_json(PEDIDOS_PATH, [])

    hoy = datetime.now(timezone.utc).date().isoformat()
    mensajes_hoy = sum(1 for l in logs if str(l.get("fecha", "")).startswith(hoy))
    resueltos = sum(1 for l in logs if not l.get("escalar"))
    escalados = sum(1 for l in logs if l.get("escalar"))
    pedidos_pendientes = sum(1 for p in pedidos if p.get("estado") == "pendiente")
    ingresos_confirmados = sum(
        p.get("total", 0) for p in pedidos if p.get("estado") == "confirmado"
    )

    return {
        "mensajes_hoy": mensajes_hoy,
        "resueltos": resueltos,
        "escalados": escalados,
        "total_conversaciones": resueltos + escalados,
        "pedidos_pendientes": pedidos_pendientes,
        "ingresos_confirmados": ingresos_confirmados,
    }


@app.get("/api/pedidos/excel")
def descargar_pedidos_excel():
    """Descarga el Excel con todos los pedidos (data/pedidos.xlsx)."""
    if not PEDIDOS_XLSX_PATH.exists():
        raise HTTPException(status_code=404, detail="Todavía no hay pedidos registrados en Excel")
    return FileResponse(
        PEDIDOS_XLSX_PATH,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="pedidos.xlsx",
    )


def obtener_url_publica(request: Request) -> str:
    """Devuelve la URL pública del sistema (sin / al final).

    Si está configurada la variable de entorno PUBLIC_URL (la URL que da
    ngrok), esa manda siempre, sin importar cómo se haya abierto la página
    que la pide -- así el QR nunca apunta por error a localhost. Si no está
    configurada, usa la misma URL/host con la que se accedió a esta
    request (sirve para probar por IP local sin ngrok)."""
    base = os.getenv("PUBLIC_URL")
    return base.rstrip("/") if base else str(request.base_url).rstrip("/")


@app.get("/api/bienvenida")
def bienvenida():
    """Mensaje de bienvenida y sugerencias que muestran el WhatsApp y el
    Instagram simulados apenas se abre el chat (por ejemplo, al escanear el
    QR). Se editan en data/negocio.json ("bienvenida" y "sugerencias");
    {nombre} se reemplaza por el nombre del negocio."""
    negocio = leer_json(NEGOCIO_PATH, {})
    nombre = negocio.get("nombre", "nuestro negocio")
    texto = negocio.get(
        "bienvenida",
        "¡Hola! 👋 Bienvenido/a a {nombre}. ¿En qué te puedo ayudar?",
    )
    return {
        "mensaje": texto.replace("{nombre}", nombre),
        "sugerencias": negocio.get("sugerencias", []),
    }


@app.get("/api/public-url")
def public_url(request: Request):
    """La URL pública que está usando el sistema ahora mismo. La usa
    qr.html para mostrar en pantalla a dónde apunta el QR, y así detectar
    a simple vista si falta configurar PUBLIC_URL."""
    return {"url": obtener_url_publica(request)}


# A qué pantalla apunta el QR de cada canal.
PAGINAS_QR = {"whatsapp": "whatsapp.html", "instagram": "instagram.html"}


def generar_qr(url: str) -> StreamingResponse:
    img = qrcode.make(url, box_size=10, border=2)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png")


@app.get("/api/qr/{canal}")
def qr_canal(canal: str, request: Request):
    """Genera un QR que apunta al WhatsApp o al Instagram simulado
    (/api/qr/whatsapp o /api/qr/instagram), siempre usando
    obtener_url_publica() para que coincida con /api/public-url."""
    pagina = PAGINAS_QR.get(canal)
    if pagina is None:
        raise HTTPException(status_code=404, detail="Canal desconocido (usá whatsapp o instagram)")
    return generar_qr(f"{obtener_url_publica(request)}/{pagina}")


@app.get("/api/qr-whatsapp")
def qr_whatsapp(request: Request):
    """Se mantiene por compatibilidad: igual que /api/qr/whatsapp."""
    return qr_canal("whatsapp", request)


@app.post("/api/pedidos/{pedido_id}/estado")
def actualizar_estado_pedido(pedido_id: str, payload: EstadoPedido):
    pedidos = leer_json(PEDIDOS_PATH, [])
    pedido = next((p for p in pedidos if p["id"] == pedido_id), None)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    pedido["estado"] = payload.estado
    guardar_json(PEDIDOS_PATH, pedidos)
    # Mantiene sincronizado el Excel que se descarga desde el panel, que
    # antes se quedaba siempre en "pendiente" aunque se confirmara/rechazara
    # el pedido en pedidos.json.
    actualizar_estado_pedido_excel(pedido_id, payload.estado)
    return pedido


@app.get("/")
def index():
    return FileResponse(PUBLIC_DIR / "index.html")


# Sirve whatsapp.html, whatsapp.js, dashboard.html, dashboard.js, etc.
app.mount("/", StaticFiles(directory=PUBLIC_DIR), name="public")
