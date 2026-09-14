"""
main.py

Servidor FastAPI del agente. Expone:
- El WhatsApp simulado (public/whatsapp.html) -> POST /api/chat
- El webhook real de WhatsApp vía Meta WhatsApp Cloud API -> /webhook/meta
- El webhook real de WhatsApp vía Twilio Sandbox (alternativa) -> POST /webhook/whatsapp
- El panel del dueño (public/dashboard.html) -> GET /api/logs, /api/pedidos
"""

import os
from pathlib import Path
from xml.sax.saxutils import escape

from dotenv import load_dotenv

# Cargar .env ANTES de importar agent, para que las variables de entorno
# ya estén disponibles si algún módulo las necesita al importarse.
load_dotenv()

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import leer_json, guardar_json, responder_mensaje, LOGS_PATH, PEDIDOS_PATH
from meta_whatsapp import enviar_mensaje_whatsapp

BASE_DIR = Path(__file__).resolve().parent
PUBLIC_DIR = BASE_DIR / "public"

app = FastAPI(title="Agente IA - Kiosco")


class MensajeChat(BaseModel):
    cliente: str
    mensaje: str


class EstadoPedido(BaseModel):
    estado: str  # "confirmado" | "rechazado"


@app.post("/api/chat")
async def chat(payload: MensajeChat):
    """Usado por el WhatsApp simulado en el navegador."""
    resultado = await responder_mensaje(payload.cliente, payload.mensaje, "whatsapp-simulado")
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


@app.get("/api/logs")
def obtener_logs():
    return leer_json(LOGS_PATH, [])


@app.get("/api/pedidos")
def obtener_pedidos():
    return leer_json(PEDIDOS_PATH, [])


@app.post("/api/pedidos/{pedido_id}/estado")
def actualizar_estado_pedido(pedido_id: str, payload: EstadoPedido):
    pedidos = leer_json(PEDIDOS_PATH, [])
    pedido = next((p for p in pedidos if p["id"] == pedido_id), None)
    if pedido is None:
        raise HTTPException(status_code=404, detail="Pedido no encontrado")
    pedido["estado"] = payload.estado
    guardar_json(PEDIDOS_PATH, pedidos)
    return pedido


@app.get("/")
def index():
    return FileResponse(PUBLIC_DIR / "index.html")


# Sirve whatsapp.html, whatsapp.js, dashboard.html, dashboard.js, etc.
app.mount("/", StaticFiles(directory=PUBLIC_DIR), name="public")
