// Simula la app de WhatsApp: manda el mensaje del "cliente" al agente
// (POST /api/chat) y muestra la respuesta como si fuera una conversación real.

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

async function enviarMensaje() {
  const texto = input.value.trim();
  if (!texto) return;

  agregarBurbuja(texto, "cliente");
  input.value = "";
  botonEnviar.disabled = true;
  estadoEl.textContent = "escribiendo...";

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cliente: idCliente(), mensaje: texto }),
    });
    const data = await res.json();

    agregarBurbuja(data.respuesta, "agente", data.escalar);
    if (data.escalar) {
      agregarAviso("🔔 Se avisó a un encargado humano para que revise esta conversación");
    }
    if (data.pedido) {
      agregarAviso("🛒 Pedido registrado, a la espera de confirmación del encargado");
    }
  } catch (err) {
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
