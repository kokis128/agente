# 🤖 Agente de IA para un kiosco (proyecto de expo)

Un agente de inteligencia artificial que atiende WhatsApp e Instagram para un
kiosco/almacén: responde preguntas frecuentes, cotiza productos del catálogo,
toma pedidos, y avisa a un humano cuando no puede resolver algo solo. Incluye
un panel para que el "dueño del negocio" supervise en vivo todo lo que
contesta el agente, en ambos canales.

## Arquitectura

```
Cliente (WhatsApp o Instagram, real o simulado)
        │
        ▼
   FastAPI (main.py)  ──────────────┐
        │                           │
        ▼                           ▼
   agent.py (el "cerebro")     panel del dueño
        │                     (public/dashboard.html)
        ▼
   Gemini API (Google, gratis)
        │
        ▼
data/negocio.json + data/productos.json  (lo que el agente "sabe")
data/logs.json + data/pedidos.json       (lo que el agente "hizo")
```

- **main.py**: servidor FastAPI. Recibe mensajes desde varios canales (WhatsApp
  simulado, WhatsApp real vía Meta Cloud API, Instagram simulado, Instagram
  real vía Meta) y expone el panel del dueño.
- **agent.py**: arma el contexto del negocio, le pregunta a Gemini, y decide si
  hay que escalar a un humano o registrar un pedido -- es el mismo "cerebro"
  sin importar de qué canal vino el mensaje.
- **meta_whatsapp.py**: manda la respuesta del agente por WhatsApp real usando
  la API de Meta (solo se usa si configuran el webhook del punto 5).
- **instagram_meta.py**: igual que meta_whatsapp.py pero para Instagram Direct
  (solo se usa si configuran el webhook del punto 6).
- **data/**: la "base de datos" del proyecto, en archivos JSON simples (sin
  necesidad de instalar una base de datos real).
- **public/**: las pantallas (WhatsApp simulado, Instagram simulado y panel
  del dueño).

## 1. Instalación

Necesitás Python 3.10 o superior.

```bash
python -m venv .venv
```

Activar el entorno virtual:

- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
- Windows (Git Bash): `source .venv/Scripts/activate`
- Linux/Mac: `source .venv/bin/activate`

Instalar dependencias:

```bash
pip install -r requirements.txt
```

## 2. Conseguir la API key gratuita de Gemini

1. Entrar a https://aistudio.google.com/app/apikey con una cuenta de Google.
2. Crear una API key (es gratis, tiene un límite de usos por minuto/día que
   alcanza de sobra para la demo).
3. Copiar `.env.example` como `.env`:
   ```bash
   cp .env.example .env
   ```
4. Pegar la key en `.env`:
   ```
   GEMINI_API_KEY=tu_clave_aca
   ```

## 3. Correr el proyecto

```bash
uvicorn main:app --reload --port 8000
```

Abrir en el navegador:

- http://localhost:8000 → pantalla de inicio
- http://localhost:8000/whatsapp.html → WhatsApp simulado (cliente)
- http://localhost:8000/instagram.html → Instagram simulado (cliente)
- http://localhost:8000/dashboard.html → panel del dueño

**Tip para la demo**: abrir el chat simulado y el panel en ventanas separadas,
escribir como cliente en una, y ver en la otra cómo el agente registra la
conversación en vivo (el panel se actualiza solo cada 3 segundos). Funciona
igual para WhatsApp e Instagram simulados.

## 4. Personalizar el negocio

Todo lo que "sabe" el agente está en dos archivos, sin tocar código:

- `data/negocio.json`: nombre, dirección, horario, formas de pago, envíos.
- `data/productos.json`: catálogo con precios y stock.

## 5. (Opcional / bonus) Conectar WhatsApp real con Meta WhatsApp Cloud API

Esto es **gratis** (1000 conversaciones/mes sin cargo) y no pide tarjeta de
crédito para el número de prueba, pero necesita internet estable el día de la
demo. Como respaldo, siempre pueden mostrar la versión simulada.

> Nota: Twilio también ofrece WhatsApp, pero muchas cuentas nuevas ahora piden
> tarjeta para verificar identidad incluso para el modo de prueba. Por eso
> recomendamos ir directo con Meta, que es el dueño de WhatsApp.

### Paso 1 — Crear la app en Meta

1. Entrar a https://developers.facebook.com/ con una cuenta de Facebook y
   crear una cuenta de developer (gratis).
2. **Mis apps → Crear app → tipo "Otro" → "Empresa"**. Ponerle cualquier
   nombre (ej. "Kiosco Don Valentini").
3. Dentro de la app, buscar el producto **WhatsApp** y agregarlo ("Set up").

### Paso 2 — Conseguir los datos que pide `.env`

En la página de **WhatsApp → Configuración de la API** (API Setup) vas a ver:

- Un **número de prueba** gratuito ya creado por Meta y su **Phone number ID**
  → pegarlo en `WHATSAPP_PHONE_NUMBER_ID`.
- Un **token de acceso temporal** (dura 24hs, alcanza para probar en la expo;
  si quieren uno que no venza, hay que generar un token permanente con un
  "System User", es un paso extra que pueden googlear si les interesa)
  → pegarlo en `WHATSAPP_ACCESS_TOKEN`.
- Ahí mismo, en **"To"**, agregar el número de celular de quien vaya a probar
  el chat (hasta 5 números). Les va a llegar un código por WhatsApp para
  verificarlo — sin este paso Meta no les deja mandarles mensajes.

`WHATSAPP_VERIFY_TOKEN` lo inventan ustedes: cualquier palabra secreta, por
ejemplo `kiosco2026`.

### Paso 3 — Exponer el servidor y configurar el webhook

1. Instalar [ngrok](https://ngrok.com/download) (gratis) y correr:
   ```bash
   ngrok http 8000
   ```
   Copiar la URL pública que da, tipo `https://algo.ngrok-free.app`.
2. En Meta, ir a **WhatsApp → Configuration → Webhook → Edit**.
3. Completar:
   - **Callback URL**: `https://algo.ngrok-free.app/webhook/meta`
   - **Verify token**: la misma palabra que pusieron en `WHATSAPP_VERIFY_TOKEN`
4. Hacer clic en **Verify and save** (nuestro servidor tiene que estar
   corriendo en ese momento para que la verificación funcione).
5. Suscribirse al campo **messages** (webhook fields → Manage → tildar "messages").

### Paso 4 — Probar

Desde el celular que verificaron en el Paso 2, escribirle por WhatsApp al
número de prueba de Meta. El mensaje va a llegar al webhook, el agente lo va
a procesar igual que en la demo simulada, y la respuesta va a volver por
WhatsApp de verdad.

## 6. (Opcional / bonus) Conectar Instagram real con Instagram Messaging API

También gratis, y reutiliza la **misma app de Meta for Developers** que ya
crearon para WhatsApp -- no hace falta crear una app nueva. Como con
WhatsApp, siempre queda como respaldo la demo simulada (`/instagram.html`).

> Requisito: una cuenta de Instagram **profesional** (business o creador)
> vinculada a la misma página de Facebook que usan para WhatsApp. Si ya la
> tenían vinculada antes de este paso, van directo al Paso 2.

### Paso 1 — Agregar el producto Instagram a la app

1. Entrar a la misma app que ya tienen en
   [developers.facebook.com](https://developers.facebook.com/apps).
2. Buscar el producto **Instagram** y agregarlo ("Set up"), igual que
   hicieron con WhatsApp.

### Paso 2 — Conseguir el token que pide `.env`

En **Instagram → API Setup with Facebook Login** (el nombre exacto puede
variar un poco según cuándo lo abran, Meta cambia la interfaz seguido) van a
poder generar un **token de acceso** para la cuenta de Instagram vinculada
→ pegarlo en `INSTAGRAM_ACCESS_TOKEN`.

`INSTAGRAM_VERIFY_TOKEN` es opcional: si lo dejan vacío, el webhook de
Instagram reutiliza el mismo `WHATSAPP_VERIFY_TOKEN` que ya configuraron
(total es la misma app). Solo hace falta uno propio si quieren un valor
distinto.

### Paso 3 — Configurar el webhook

1. Con `ngrok http 8000` corriendo (el mismo que usan para WhatsApp), ir a
   **Instagram → Webhooks** dentro de la app.
2. Completar:
   - **Callback URL**: `https://algo.ngrok-free.app/webhook/instagram`
   - **Verify token**: el mismo valor de `WHATSAPP_VERIFY_TOKEN` (o el de
     `INSTAGRAM_VERIFY_TOKEN` si pusieron uno distinto)
3. **Verify and save** (el servidor tiene que estar corriendo).
4. Suscribirse al campo **messages** para esa cuenta de Instagram.

### Paso 4 — Probar

Desde otra cuenta de Instagram (no la del negocio), mandarle un DM a la
cuenta profesional. El mensaje llega al webhook, el agente lo procesa igual
que en la demo simulada, y contesta por Instagram Direct de verdad.

## 7. Intervención humana (el encargado toma la conversación)

Cuando el agente no puede resolver algo (el cliente pide hablar con una
persona, hace un reclamo, pregunta algo fuera del catálogo), **le pasa la
conversación al encargado y se queda callado** en ese chat:

1. El cliente recibe el aviso "Te pasamos con un encargado".
2. En el panel del dueño aparece un cartel naranja y la conversación en la
   sección **🙋 Atención humana**.
3. El encargado abre la conversación, ve todo lo que se habló y le escribe
   al cliente. El mensaje le llega por el mismo canal (chat simulado,
   WhatsApp real o Instagram real) con la etiqueta "👤 Encargado".
4. Cuando termina, toca **"Devolver al agente 🤖"** y el agente vuelve a
   contestar, sabiendo lo que dijo el encargado.

El encargado también puede **tomar cualquier conversación** aunque el agente
no lo haya pedido (botón "Atender" en la tabla de conversaciones).

Los errores técnicos (Gemini caído, falta la API key) se marcan en rojo pero
**no** pausan al agente, para que la demo no quede muda si nadie mira el
panel. Si prefieren que el agente nunca se pause solo, cambien
`PAUSAR_AGENTE_AL_ESCALAR = False` en `agent.py`.

**Para mostrarlo en la expo**: en el WhatsApp simulado escribir "quiero
hablar con una persona", y desde el panel contestarle como encargado.

## Solución de problemas

**El agente siempre contesta "Uy, tuve un problema técnico..."**

Eso significa que falló la llamada a Gemini. Para ver el motivo real:

1. Abrir el panel del dueño (`/dashboard.html`) y pasar el mouse por encima
   del badge rojo "Requiere humano" de esa conversación — el motivo exacto
   aparece en un tooltip.
2. O mirar la consola donde corre `uvicorn`: el error se imprime ahí también.

La causa más común es que **Google renombra o da de baja modelos de Gemini**
con el tiempo. Si el error dice algo como *"this model is no longer
available"*, hay que cambiar `GEMINI_MODEL` en `.env` por un modelo vigente.
Para ver la lista actualizada de modelos disponibles con su clave, pueden
correr esto (reemplazando `TU_API_KEY`):

```bash
curl "https://generativelanguage.googleapis.com/v1beta/models?key=TU_API_KEY"
```

Buscar en la respuesta un modelo cuyo nombre contenga `flash` y que soporte
`generateContent`.

**Ojo con los alias "-latest" (ej. `gemini-flash-lite-latest`)**: probamos uno
y a veces enrutaba a un modelo mucho más lento (30-45 segundos por respuesta),
sin ningún error — simplemente tardaba una eternidad. Por eso el proyecto
viene configurado con un modelo fijo (`gemini-3.1-flash-lite`), que en las
pruebas respondió siempre en 1-7 segundos. Si en el futuro ese modelo deja de
existir, mejor elegir otro nombre de modelo fijo (sin "-latest") de la lista
de arriba, en vez de un alias.

**El WhatsApp o el Instagram real no mandan nada**

El panel del dueño (`/dashboard.html`) muestra un cartel rojo arriba de todo
apenas detecta que el último envío falló (token vencido, falta configurar,
etc.), tanto para WhatsApp como para Instagram -- no hace falta ir a mirar la
consola. La causa más común en ambos es el **token de acceso vencido**: el
que se genera desde "API Setup" en Meta for Developers suele ser temporal
(dura 24hs); para la expo conviene generar uno permanente (System User),
como se menciona en los pasos de arriba.

## Ideas para explicar en la expo

- **Por qué "agente" y no solo "chatbot"**: el sistema no solo conversa, además
  *decide* cosas (si escalar a un humano, si registrar un pedido) y *actúa*
  sobre datos reales (consulta stock y precios).
- **El rol del humano**: mostrar el panel del dueño y explicar que ningún
  pedido se confirma solo — siempre lo aprueba una persona. Esto es justamente
  cómo se usan los agentes de IA en empresas reales: el agente hace el trabajo
  repetitivo, pero un humano supervisa las decisiones importantes.
- **De dónde saca la información**: mostrar `data/productos.json` y explicar
  que ahí es donde "vive" el conocimiento del agente — si cambian un precio ahí,
  el agente lo usa en la próxima respuesta, sin tocar código.
