// Simula la app de Instagram: manda el mensaje del "cliente" al agente
// (POST /api/chat, canal "instagram-simulado") y muestra la respuesta como
// si fuera un DM real, con indicador de "escribiendo..." animado.

const contenedor = document.getElementById("mensajes");
const input = document.getElementById("input");
const botonEnviar = document.getElementById("enviar");
const estadoEl = document.getElementById("estado");

// Cada pestaña del navegador simula un cliente distinto.
function idCliente() {
  let id = sessionStorage.getItem("clienteIdInstagram");
  if (!id) {
    id = "ig-" + Math.random().toString(36).slice(2, 8);
    sessionStorage.setItem("clienteIdInstagram", id);
  }
  return id;
}

function horaActual() {
  return new Date().toLocaleTimeString("es-AR", { hour: "2-digit", minute: "2-digit" });
}

function agregarBurbuja(texto, tipo, escalado = false) {
  const burbuja = document.createElement("div");
  burbuja.className = `burbuja ${tipo}` + (escalado ? " escalado" : "");
  burbuja.textContent = texto;

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
      body: JSON.stringify({ cliente: idCliente(), mensaje: texto, canal: "instagram-simulado" }),
    });
    const data = await res.json();

    ocultarEscribiendo();
    agregarBurbuja(data.respuesta, "agente", data.escalar);
    if (data.escalar) {
      agregarAviso("🔔 Se avisó a un encargado humano para que revise esta conversación");
    }
    if (data.pedido) {
      agregarAviso("🛒 Pedido registrado, a la espera de confirmación del encargado");
    }
  } catch (err) {
    ocultarEscribiendo();
    agregarBurbuja("No se pudo conectar con el agente. ¿Está corriendo el servidor?", "agente", true);
  } finally {
    estadoEl.textContent = "activo ahora";
    botonEnviar.disabled = false;
    input.focus();
  }
}

botonEnviar.addEventListener("click", enviarMensaje);
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter") enviarMensaje();
});

agregarAviso("Los mensajes de este chat simulan lo que un cliente escribiría por Instagram Direct");

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
    estadoEl.textContent = "activo ahora";
  }
}

mostrarBienvenida();
