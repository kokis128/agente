// Simula la app de WhatsApp: manda el mensaje del "cliente" al agente
// (POST /api/chat) y muestra la respuesta como si fuera una conversación real,
// con indicador de "escribiendo..." animado mientras el agente responde.

const contenedor = document.getElementById("mensajes");
const input = document.getElementById("input");
const botonEnviar = document.getElementById("enviar");
const estadoEl = document.getElementById("estado");

// Cada pestaña del navegador simula un cliente distinto.
function idCliente() {
  let id = sessionStorage.getItem("clienteId");
  if (!id) {
    id = "web-" + Math.random().toString(36).slice(2, 8);
    sessionStorage.setItem("clienteId", id);
  }
  return id;
}

function horaActual() {
  return new Date().toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
}

function agregarBurbuja(texto, tipo, escalado = false, autor = "") {
  const burbuja = document.createElement("div");
  burbuja.className = `burbuja ${tipo}` + (escalado ? " escalado" : "") + (autor ? " humano" : "");
  if (autor) {
    const quien = document.createElement("div");
    quien.className = "autor";
    quien.textContent = autor;
    burbuja.appendChild(quien);
  }
  burbuja.appendChild(document.createTextNode(texto));

  const hora = document.createElement("div");
  hora.className = "hora";
  hora.textContent = horaActual();
  burbuja.appendChild(hora);

  contenedor.appendChild(burbuja);
  contenedor.scrollTop = contenedor.scrollHeight;
}

function agregarAviso(texto) {
  const aviso = document.createElement("div");
  aviso.className = "aviso";
  aviso.textContent = texto;
  contenedor.appendChild(aviso);
  contenedor.scrollTop = contenedor.scrollHeight;
}

function mostrarEscribiendo() {
  const burbuja = document.createElement("div");
  burbuja.className = "escribiendo";
  burbuja.id = "burbuja-escribiendo";
  burbuja.innerHTML = '<span class="punto"></span><span class="punto"></span><span class="punto"></span>';
  contenedor.appendChild(burbuja);
  contenedor.scrollTop = contenedor.scrollHeight;
}

function ocultarEscribiendo() {
  const burbuja = document.getElementById("burbuja-escribiendo");
  if (burbuja) burbuja.remove();
}

async function enviarMensaje() {
  const texto = input.value.trim();
  if (!texto) return;

  quitarSugerencias();
  agregarBurbuja(texto, "cliente");
  input.value = "";
  botonEnviar.disabled = true;
  estadoEl.textContent = "escribiendo...";
  mostrarEscribiendo();

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cliente: idCliente(), mensaje: texto }),
    });
    const data = await res.json();

    ocultarEscribiendo();
    // Si lo está atendiendo una persona, el agente no contesta (respuesta vacía).
    if (data.respuesta) {
      agregarBurbuja(data.respuesta, "agente", data.escalar);
    }
    if (data.en_manos_humano) {
      cambiarModoHumano(true);
    } else if (data.escalar) {
      agregarAviso("🔔 Se avisó a un encargado humano para que revise esta conversación");
    }
    if (data.pedido) {
      agregarAviso("🛒 Pedido registrado, a la espera de confirmación del encargado");
    }
  } catch (err) {
    ocultarEscribiendo();
    agregarBurbuja("No se pudo conectar con el agente. ¿Está corriendo el servidor?", "agente", true);
  } finally {
    estadoEl.textContent = "en línea";
    botonEnviar.disabled = false;
    input.focus();
  }
}

botonEnviar.addEventListener("click", enviarMensaje);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") enviarMensaje();
});

agregarAviso("Los mensajes de este chat simulan lo que un cliente escribiría por WhatsApp");

// --- Bienvenida automática ---
// Apenas se abre el chat (por ejemplo, al escanear el QR), el agente
// "escribe" un saludo con sugerencias tocables. El texto sale de
// data/negocio.json vía /api/bienvenida. Solo se muestra una vez por pestaña.
function mostrarSugerencias(sugerencias) {
  if (!sugerencias || !sugerencias.length) return;
  const caja = document.createElement("div");
  caja.className = "sugerencias";
  caja.id = "sugerencias";
  sugerencias.forEach((texto) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = texto;
    chip.addEventListener("click", () => {
      input.value = texto;
      enviarMensaje();
    });
    caja.appendChild(chip);
  });
  contenedor.appendChild(caja);
  contenedor.scrollTop = contenedor.scrollHeight;
}

function quitarSugerencias() {
  const caja = document.getElementById("sugerencias");
  if (caja) caja.remove();
}

async function mostrarBienvenida() {
  const clave = "bienvenidaVista-" + location.pathname;
  if (sessionStorage.getItem(clave)) return;
  sessionStorage.setItem(clave, "1");
  estadoEl.textContent = "escribiendo...";
  mostrarEscribiendo();
  try {
    const [res] = await Promise.all([
      fetch("/api/bienvenida"),
      new Promise((r) => setTimeout(r, 1200)),
    ]);
    const data = await res.json();
    ocultarEscribiendo();
    agregarBurbuja(data.mensaje, "agente");
    mostrarSugerencias(data.sugerencias);
  } catch (err) {
    ocultarEscribiendo();
  } finally {
    estadoEl.textContent = "en línea";
  }
}

mostrarBienvenida();

// --- Intervención humana ---
// Cuando el agente pasa la conversación a un encargado (o el encargado la
// toma desde el panel), lo que escribe el encargado llega acá. El navegador
// pregunta cada 2,5 segundos si hay mensajes nuevos de una persona.
let atendidoPorHumano = false;

function cambiarModoHumano(activo) {
  if (activo === atendidoPorHumano) return;
  atendidoPorHumano = activo;
  agregarAviso(
    activo
      ? "👤 Te pasamos con un encargado. Te va a responder una persona por este chat."
      : "🤖 El encargado terminó. Te vuelve a atender el asistente virtual."
  );
}

async function buscarNovedades() {
  try {
    const res = await fetch(`/api/chat/novedades?cliente=${encodeURIComponent(idCliente())}`);
    const data = await res.json();
    if (data.en_manos_humano) cambiarModoHumano(true);
    (data.mensajes || []).forEach((m) => agregarBurbuja(m.texto, "agente", false, "👤 Encargado"));
    if (!data.en_manos_humano) cambiarModoHumano(false);
  } catch {
    // si el servidor no responde, se reintenta en el próximo ciclo
  }
}

setInterval(buscarNovedades, 2500);
