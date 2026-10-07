"""
agent.py

Aca vive el "cerebro" del agente: arma el contexto del negocio,
llama a Gemini, interpreta la respuesta y decide si hay que
avisarle a un humano (escalar) o registrar un pedido.
"""

import asyncio
import json
import os
import random
import string
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
NEGOCIO_PATH = DATA_DIR / "negocio.json"
PRODUCTOS_PATH = DATA_DIR / "productos.json"
LOGS_PATH = DATA_DIR / "logs.json"
PEDIDOS_PATH = DATA_DIR / "pedidos.json"
PEDIDOS_XLSX_PATH = DATA_DIR / "pedidos.xlsx"
WHATSAPP_STATUS_PATH = DATA_DIR / "whatsapp_status.json"
INSTAGRAM_STATUS_PATH = DATA_DIR / "instagram_status.json"
# Conversaciones que tomo un encargado humano (el agente no contesta en esas).
INTERVENCIONES_PATH = DATA_DIR / "intervenciones.json"

# Si es True, cuando el agente decide escalar (el cliente pide una persona,
# hace un reclamo, etc.) la conversacion pasa sola a manos del encargado y el
# agente deja de contestar hasta que alguien la devuelva desde el panel.
# Los errores tecnicos (Gemini caido, falta la API key) NO pausan al agente:
# solo se marcan en rojo, para que la demo no se quede muda si nadie mira.
PAUSAR_AGENTE_AL_ESCALAR = True

DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"

# Modelos de respaldo: si el modelo principal esta saturado (503 "high
# demand") o se quedo sin cupo (429), se prueba con estos en orden antes de
# avisarle al cliente que hubo un problema. Se pueden cambiar en .env con
# GEMINI_MODELOS_RESPALDO=modelo1,modelo2
DEFAULT_MODELOS_RESPALDO = "gemini-3.5-flash-lite,gemini-3.5-flash"

# Gemini (sobre todo en el tier gratis) devuelve 503 "alta demanda" o un
# 429 de limite de uso de vez en cuando -- son errores transitorios que la
# propia Google recomienda reintentar ("please try again later"), asi que
# antes de rendirse y avisarle al cliente que hubo un problema, reintentamos
# unas pocas veces con una espera corta entre intentos.
MAX_INTENTOS_GEMINI = 3
ESPERA_BASE_REINTENTO_SEGUNDOS = 1.5
CODIGOS_TRANSITORIOS_GEMINI = {429, 500, 503}

# Historial de conversacion por cliente (en memoria; alcanza para la demo).
# clave: id de sesion (telefono simulado o numero real de WhatsApp)
historiales: dict[str, list[dict]] = {}

# Guarda el ultimo pedido registrado por cliente (en memoria) para no
# duplicarlo si el modelo vuelve a incluirlo en mensajes siguientes de la
# misma conversacion (ej: el cliente agradece o pregunta otra cosa y Gemini
# repite el resumen del pedido en su respuesta JSON).
# clave: cliente -> {"items": tupla normalizada, "total": float, "ts": epoch}
ultimos_pedidos_registrados: dict[str, dict] = {}

# Ultimo canal por el que escribio cada cliente, para saber por donde
# mandarle la respuesta del encargado humano (WhatsApp real, Instagram real
# o los chats simulados del navegador).
ultimo_canal: dict[str, str] = {}

# Mensajes del encargado que todavia no vio un cliente de los chats
# simulados (el navegador los viene a buscar cada pocos segundos).
bandeja_simulados: dict[str, list[dict]] = {}
VENTANA_DEDUPE_PEDIDO_SEGUNDOS = 1800  # 30 minutos


class ItemPedido(BaseModel):
    producto: str
    cantidad: float


class Pedido(BaseModel):
    items: list[ItemPedido] = []
    total: float = 0


class ResultadoAgente(BaseModel):
    respuesta: str
    escalar: bool = False
    motivo: str = ""
    pedido: Optional[Pedido] = None
    # True cuando la conversacion la esta atendiendo un humano: el agente no
    # contesto nada y "respuesta" viene vacia.
    en_manos_humano: bool = False


def leer_json(path: Path, valor_por_defecto):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return valor_por_defecto


def guardar_json(path: Path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def construir_system_prompt() -> str:
    negocio = leer_json(NEGOCIO_PATH, {})
    productos = leer_json(PRODUCTOS_PATH, [])

    catalogo = "\n".join(
        f"- {p['nombre']} ({p['categoria']}): ${p['precio']} | stock: {p['stock']} unidades"
        for p in productos
    )

    return f"""Sos el asistente virtual de "{negocio.get('nombre')}", un kiosco/almacen de barrio.
Atendes a clientes por WhatsApp e Instagram (mensajes directos). Hablá en español rioplatense, de forma breve, amable y natural,
como lo haría un empleado del kiosco. No uses lenguaje robótico ni te presentes como "modelo de IA".

DATOS DEL NEGOCIO:
- Dirección: {negocio.get('direccion')}
- Horario: {negocio.get('horario')}
- Formas de pago: {negocio.get('formasDePago')}
- Envíos: {negocio.get('envios')}

CATÁLOGO Y PRECIOS ACTUALES:
{catalogo}

REGLAS IMPORTANTES:
1. Solo respondé con información real del catálogo y los datos del negocio de arriba. Si te preguntan
   por un producto que NO está en el catálogo, decilo con honestidad y no inventes precio ni stock.
2. Si el cliente quiere hacer un pedido, confirmá los productos, cantidades y el total, y marcalo
   como pedido. Hacé esto SOLO en el mensaje donde confirmás ese pedido por primera vez. En los
   mensajes siguientes de la misma conversación (el cliente agradece, pregunta otra cosa, saluda,
   etc.) dejá "pedido" en null -- no repitas el mismo pedido de nuevo. Si el cliente agrega o
   cambia productos, ahí sí mandá el pedido actualizado completo (con todos los items, no solo los
   nuevos).
3. Marcá "escalar": true (para que un empleado humano intervenga) cuando:
   - El cliente pide algo que no podés resolver vos (reclamos, devoluciones, preguntas raras, precios
     especiales, algo fuera del catálogo).
   - El cliente parece enojado, urgente, o insiste en hablar con una persona.
   - No estás seguro de la respuesta.
   Cuando escales, en "respuesta" avisale al cliente que lo pasás con un encargado y que le va a
   escribir por este mismo chat en un ratito (no le hagas más preguntas en ese mensaje).
5. Si en el historial ves mensajes que empiezan con "[Encargado]", los escribió una persona del
   kiosco. Respetá lo que haya dicho o acordado el encargado y seguí desde ahí.
4. Nunca confirmes definitivamente un pedido como "entregado" ni proceses pagos: solo tomá el pedido,
   avisá que un encargado lo va a confirmar, y marcá "pedido" con el detalle.

FORMATO DE RESPUESTA:
Respondé SIEMPRE y ÚNICAMENTE con un JSON válido, sin texto extra, con esta forma exacta:
{{
  "respuesta": "el mensaje de texto que le vas a mandar al cliente por WhatsApp",
  "escalar": true o false,
  "motivo": "si escalar es true, explicá brevemente por qué; si es false, dejalo vacío",
  "pedido": null o {{ "items": [{{"producto": "nombre", "cantidad": numero}}], "total": numero }}
}}"""


async def _post_gemini_con_reintentos(client: httpx.AsyncClient, url: str, body: dict) -> httpx.Response:
    """Manda el POST a Gemini reintentando si la respuesta es un error
    transitorio (503/429/500) o si falla la conexion/timeout. No reintenta
    errores permanentes (401 token invalido, 404 modelo no existe, etc.) --
    esos se devuelven tal cual en el primer intento."""
    ultima_respuesta = None
    for intento in range(1, MAX_INTENTOS_GEMINI + 1):
        es_ultimo_intento = intento == MAX_INTENTOS_GEMINI
        try:
            ultima_respuesta = await client.post(url, json=body)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            if es_ultimo_intento:
                raise
            print(
                f"[agent] Intento {intento}/{MAX_INTENTOS_GEMINI} a Gemini fallo por red "
                f"({type(e).__name__}), reintentando..."
            )
        else:
            if ultima_respuesta.status_code not in CODIGOS_TRANSITORIOS_GEMINI or es_ultimo_intento:
                return ultima_respuesta
            print(
                f"[agent] Intento {intento}/{MAX_INTENTOS_GEMINI} a Gemini fallo con "
                f"{ultima_respuesta.status_code} (error transitorio), reintentando..."
            )
        await asyncio.sleep(ESPERA_BASE_REINTENTO_SEGUNDOS * intento)
    return ultima_respuesta


def _historial_para_gemini(historial: list[dict]) -> list[dict]:
    """Convierte el historial al formato de Gemini, juntando mensajes
    seguidos del mismo rol (pasa cuando el cliente escribio varias veces
    mientras lo atendia un humano) para que los turnos queden alternados."""
    contents: list[dict] = []
    for m in historial:
        if contents and contents[-1]["role"] == m["role"]:
            contents[-1]["parts"][0]["text"] += "\n" + m["texto"]
        else:
            contents.append({"role": m["role"], "parts": [{"text": m["texto"]}]})
    return contents


async def llamar_gemini(system_prompt: str, historial: list[dict]) -> ResultadoAgente:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return ResultadoAgente(
            respuesta=(
                "(El agente todavía no tiene configurada la GEMINI_API_KEY en el archivo .env. "
                "Agregala para que pueda responder.)"
            ),
            escalar=True,
            motivo="Falta configurar la API key de Gemini",
        )

    principal = os.getenv("GEMINI_MODEL") or DEFAULT_GEMINI_MODEL
    respaldo = os.getenv("GEMINI_MODELOS_RESPALDO", DEFAULT_MODELOS_RESPALDO)
    modelos = [principal] + [m.strip() for m in respaldo.split(",") if m.strip() and m.strip() != principal]

    body = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": _historial_para_gemini(historial),
        "generationConfig": {
            "temperature": 0.4,
            "responseMimeType": "application/json",
        },
    }

    res = None
    async with httpx.AsyncClient(timeout=45) as client:
        for i, model in enumerate(modelos):
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}"
            )
            try:
                res = await _post_gemini_con_reintentos(client, url, body)
            except (httpx.TimeoutException, httpx.TransportError):
                if i == len(modelos) - 1:
                    raise
                print(f"[agent] {model} no respondio (red/timeout), probando con {modelos[i + 1]}...")
                continue
            if res.status_code == 200:
                if i > 0:
                    print(f"[agent] Respondio el modelo de respaldo {model}")
                break
            # 401/400 = problema de la API key o del pedido: cambiar de modelo no ayuda.
            if res.status_code in (400, 401) or i == len(modelos) - 1:
                break
            print(f"[agent] {model} respondio {res.status_code}, probando con {modelos[i + 1]}...")

    if res.status_code != 200:
        raise RuntimeError(f"Gemini respondió {res.status_code}: {res.text}")

    data = res.json()
    try:
        texto = data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError):
        texto = ""

    try:
        parsed = json.loads(texto)
        return ResultadoAgente(
            respuesta=parsed.get("respuesta") or "Disculpá, no pude generar una respuesta.",
            escalar=bool(parsed.get("escalar")),
            motivo=parsed.get("motivo") or "",
            pedido=parsed.get("pedido"),
        )
    except (json.JSONDecodeError, TypeError):
        return ResultadoAgente(
            respuesta=texto or "Disculpá, tuve un problema para responder. Ya te contacta un encargado.",
            escalar=True,
            motivo="La respuesta del modelo no vino en formato válido",
        )


def registrar_log(entrada: dict):
    logs = leer_json(LOGS_PATH, [])
    logs.append(entrada)
    guardar_json(LOGS_PATH, logs)


def _abrir_o_crear_excel_pedidos():
    """Abre data/pedidos.xlsx si ya existe, o lo crea con encabezados."""
    if PEDIDOS_XLSX_PATH.exists():
        wb = load_workbook(PEDIDOS_XLSX_PATH)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "Pedidos"
        ws.append(["ID", "Fecha", "Cliente", "Productos", "Total", "Estado"])
        anchos = {"A": 22, "B": 18, "C": 16, "D": 55, "E": 10, "F": 12}
        for columna, ancho in anchos.items():
            ws.column_dimensions[columna].width = ancho
    return wb, ws


def registrar_pedido_excel(pedido_id: str, cliente: str, pedido: Pedido, fecha_iso: str, estado: str = "pendiente"):
    """Agrega una fila nueva a data/pedidos.xlsx. Si falla, no rompe el
    flujo del agente (el JSON sigue siendo la fuente de verdad)."""
    try:
        wb, ws = _abrir_o_crear_excel_pedidos()
        productos_texto = "; ".join(f"{item.cantidad}x {item.producto}" for item in pedido.items)
        fecha_legible = datetime.fromisoformat(fecha_iso).strftime("%d/%m/%Y %H:%M")
        ws.append([pedido_id, fecha_legible, cliente, productos_texto, pedido.total, estado])
        wb.save(PEDIDOS_XLSX_PATH)
    except Exception as e:
        print(f"[agent] No se pudo actualizar pedidos.xlsx: {e}")


def actualizar_estado_pedido_excel(pedido_id: str, estado: str):
    """Actualiza la columna Estado de data/pedidos.xlsx cuando el dueno
    confirma o rechaza un pedido desde el panel, para que el Excel no se
    quede desincronizado de pedidos.json (que es la fuente de verdad). Si
    falla, no rompe el flujo del panel."""
    try:
        if not PEDIDOS_XLSX_PATH.exists():
            return
        wb = load_workbook(PEDIDOS_XLSX_PATH)
        ws = wb.active
        encontrado = False
        for fila in ws.iter_rows(min_row=2):
            if fila[0].value == pedido_id:
                fila[5].value = estado  # columna F: Estado
                encontrado = True
                break
        if encontrado:
            wb.save(PEDIDOS_XLSX_PATH)
        else:
            print(f"[agent] No se encontro el pedido {pedido_id} en pedidos.xlsx para actualizar su estado")
    except Exception as e:
        print(f"[agent] No se pudo actualizar el estado en pedidos.xlsx: {e}")


def _items_normalizados(items: list[ItemPedido]) -> tuple:
    return tuple(sorted((i.producto.strip().lower(), i.cantidad) for i in items))


def _pedido_ya_registrado(cliente: str, pedido: Pedido) -> bool:
    """True si este mismo pedido (mismos productos/cantidades y mismo total)
    ya se registro hace poco para este cliente -- evita duplicar el pedido en
    pedidos.json/pedidos.xlsx cuando el modelo repite el resumen en un mensaje
    posterior de la misma conversacion."""
    anterior = ultimos_pedidos_registrados.get(cliente)
    if not anterior:
        return False
    mismo_total = abs(anterior["total"] - pedido.total) < 0.01
    mismos_items = anterior["items"] == _items_normalizados(pedido.items)
    dentro_de_ventana = (time.time() - anterior["ts"]) < VENTANA_DEDUPE_PEDIDO_SEGUNDOS
    return mismo_total and mismos_items and dentro_de_ventana


def registrar_pedido(cliente: str, pedido: Pedido):
    pedidos = leer_json(PEDIDOS_PATH, [])
    sufijo = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    pedido_id = f"{int(time.time())}-{sufijo}"
    fecha_iso = datetime.now(timezone.utc).isoformat()
    pedidos.append(
        {
            "id": pedido_id,
            "cliente": cliente,
            "items": [item.model_dump() for item in pedido.items],
            "total": pedido.total,
            "estado": "pendiente",  # pendiente | confirmado | rechazado
            "fecha": fecha_iso,
        }
    )
    guardar_json(PEDIDOS_PATH, pedidos)
    registrar_pedido_excel(pedido_id, cliente, pedido, fecha_iso)


# --- Intervencion humana -------------------------------------------------

def _ahora_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def leer_intervenciones() -> dict:
    """{cliente: {"activa": bool, "motivo": str, "desde": iso, "canal": str}}"""
    return leer_json(INTERVENCIONES_PATH, {})


def esta_en_manos_humano(cliente: str) -> bool:
    return bool(leer_intervenciones().get(cliente, {}).get("activa"))


def tomar_conversacion(cliente: str, motivo: str = "") -> dict:
    """El encargado se hace cargo: el agente deja de contestarle a este cliente."""
    intervenciones = leer_intervenciones()
    estado = {
        "activa": True,
        "motivo": motivo or "El encargado tomó la conversación desde el panel",
        "desde": _ahora_iso(),
        "canal": ultimo_canal.get(cliente) or intervenciones.get(cliente, {}).get("canal", ""),
    }
    intervenciones[cliente] = estado
    guardar_json(INTERVENCIONES_PATH, intervenciones)
    return estado


def devolver_conversacion(cliente: str) -> None:
    """El encargado termina: el agente vuelve a contestar a este cliente."""
    intervenciones = leer_intervenciones()
    if cliente in intervenciones:
        intervenciones[cliente]["activa"] = False
        intervenciones[cliente]["hasta"] = _ahora_iso()
        guardar_json(INTERVENCIONES_PATH, intervenciones)
    registrar_log(
        {
            "fecha": _ahora_iso(),
            "canal": canal_de_cliente(cliente),
            "cliente": cliente,
            "autor": "sistema",
            "mensaje": "",
            "respuesta": "El encargado devolvió la conversación al agente",
            "escalar": False,
            "motivo": "",
        }
    )


def canal_de_cliente(cliente: str) -> str:
    """Por que canal escribio este cliente la ultima vez. Si el servidor se
    reinicio y no esta en memoria, lo busca en los logs."""
    if cliente in ultimo_canal:
        return ultimo_canal[cliente]
    canal = leer_intervenciones().get(cliente, {}).get("canal")
    if not canal:
        for entrada in reversed(leer_json(LOGS_PATH, [])):
            if entrada.get("cliente") == cliente:
                canal = entrada.get("canal")
                break
    return canal or "desconocido"


def registrar_respuesta_humana(cliente: str, texto: str) -> str:
    """Guarda lo que escribio el encargado (log + historial del agente, para
    que cuando la conversacion vuelva al agente sepa lo que se hablo) y, si
    el cliente esta en un chat simulado, lo deja en su bandeja. Devuelve el
    canal del cliente para que main.py lo mande por WhatsApp/Instagram real
    cuando corresponda."""
    canal = canal_de_cliente(cliente)
    historial = historiales.setdefault(cliente, [])
    historial.append({"role": "model", "texto": f"[Encargado] {texto}"})

    if not canal.startswith(("whatsapp-real", "instagram-real")):
        bandeja_simulados.setdefault(cliente, []).append({"texto": texto, "fecha": _ahora_iso()})

    registrar_log(
        {
            "fecha": _ahora_iso(),
            "canal": canal,
            "cliente": cliente,
            "autor": "humano",
            "mensaje": "",
            "respuesta": texto,
            "escalar": False,
            "motivo": "",
        }
    )
    return canal


def retirar_mensajes_humanos(cliente: str) -> list[dict]:
    """Los chats simulados llaman a esto cada pocos segundos para ver si el
    encargado les escribio algo. Devuelve y vacia la bandeja del cliente."""
    return bandeja_simulados.pop(cliente, [])


async def responder_mensaje(cliente: str, mensaje: str, canal: str) -> ResultadoAgente:
    """Punto de entrada del agente. Se usa desde los chats simulados y desde
    los webhooks reales de WhatsApp e Instagram."""

    ultimo_canal[cliente] = canal
    historial = historiales.setdefault(cliente, [])
    historial.append({"role": "user", "texto": mensaje})

    # Si un encargado esta atendiendo esta conversacion, el agente NO
    # contesta: solo registra el mensaje para que el encargado lo vea.
    if esta_en_manos_humano(cliente):
        registrar_log(
            {
                "fecha": _ahora_iso(),
                "canal": canal,
                "cliente": cliente,
                "autor": "cliente-en-espera",
                "mensaje": mensaje,
                "respuesta": "",
                "escalar": True,
                "motivo": "Conversación en manos de un encargado",
            }
        )
        return ResultadoAgente(
            respuesta="",
            escalar=True,
            motivo="Conversación en manos de un encargado",
            en_manos_humano=True,
        )

    system_prompt = construir_system_prompt()
    error_tecnico = False

    try:
        resultado = await llamar_gemini(system_prompt, historial)
        error_tecnico = resultado.motivo.startswith("Falta configurar")
    except Exception as err:  # noqa: BLE001 - queremos degradar con gracia en la demo
        print(f"[agent] Error llamando a Gemini: {err}")
        error_tecnico = True
        resultado = ResultadoAgente(
            respuesta="Uy, tuve un problema técnico. Ya le aviso a un encargado para que te responda.",
            escalar=True,
            motivo=f"Error llamando a Gemini: {err}",
        )

    historial.append({"role": "model", "texto": resultado.respuesta})
    # Evita que el historial crezca sin límite en una demo larga.
    if len(historial) > 20:
        del historial[: len(historial) - 20]

    if resultado.pedido:
        if _pedido_ya_registrado(cliente, resultado.pedido):
            print(
                f"[agent] Pedido repetido para {cliente} (mismos items y total ya "
                "registrados hace poco), no se duplica en pedidos.json"
            )
        else:
            registrar_pedido(cliente, resultado.pedido)
            ultimos_pedidos_registrados[cliente] = {
                "items": _items_normalizados(resultado.pedido.items),
                "total": resultado.pedido.total,
                "ts": time.time(),
            }

    registrar_log(
        {
            "fecha": _ahora_iso(),
            "canal": canal,
            "cliente": cliente,
            "autor": "agente",
            "mensaje": mensaje,
            "respuesta": resultado.respuesta,
            "escalar": resultado.escalar,
            "motivo": resultado.motivo,
        }
    )

    # El agente decidio que esto lo tiene que ver una persona: le pasa la
    # conversacion al encargado y se queda callado hasta que se la devuelvan.
    if resultado.escalar and PAUSAR_AGENTE_AL_ESCALAR and not error_tecnico:
        tomar_conversacion(cliente, motivo=resultado.motivo or "El agente pidió ayuda humana")
        resultado.en_manos_humano = True

    return resultado
