// Panel del dueño: consulta periódicamente al servidor para mostrar
// en vivo lo que el agente va contestando, los pedidos que toma,
// unos KPIs animados y el estado del token de WhatsApp real.

const cuerpoPedidos = document.querySelector("#tabla-pedidos tbody");
const vacioPedidos = document.getElementById("vacio-pedidos");
const cuerpoLogs = document.querySelector("#tabla-logs tbody");
const vacioLogs = document.getElementById("vacio-logs");

let ultimoIdPedido = null;
let ultimaFechaLog = null;

function escaparHtml(texto) {
  const div = document.createElement("div");
  div.textContent = texto == null ? "" : String(texto);
  return div.innerHTML;
}

function escaparAttr(texto) {
  return escaparHtml(texto).replace(/'/g, "&#39;").replace(/"/g, "&quot;");
}

function horaLegible(iso) {
  try {
    return new Date(iso).toLocaleString("es-AR");
  } catch {
    return iso;
  }
}

function badgeEstadoPedido(estado) {
  const clase = { pendiente: "badge-pendiente", confirmado: "badge-confirmado", rechazado: "badge-rechazado" }[estado] || "badge-pendiente";
  return `<span class="badge ${clase}">${estado}</span>`;
}

async function cambiarEstadoPedido(id, estado) {
  await fetch(`/api/pedidos/${id}/estado`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ estado }),
  });
  cargarPedidos();
}

async function cargarPedidos() {
  const res = await fetch("/api/pedidos");
  const pedidos = await res.json();

  cuerpoPedidos.innerHTML = "";
  vacioPedidos.hidden = pedidos.length > 0;

  const ordenados = pedidos.slice().reverse();
  const idMasNuevo = ordenados.length ? ordenados[0].id : null;

  ordenados.forEach((p) => {
    const tr = document.createElement("tr");
    if (ultimoIdPedido !== null && p.id === idMasNuevo && p.id !== ultimoIdPedido) {
      tr.classList.add("fila-nueva");
    }
    const items = (p.items || []).map((i) => `${i.cantidad}x ${i.producto}`).join(", ");
    const acciones =
      p.estado === "pendiente"
        ? `<button class="accion confirmar" onclick="cambiarEstadoPedido('${p.id}', 'confirmado')">Confirmar</button>
           <button class="accion rechazar" onclick="cambiarEstadoPedido('${p.id}', 'rechazado')">Rechazar</button>`
        : "—";
    tr.innerHTML = `
      <td>${horaLegible(p.fecha)}</td>
      <td>${p.cliente}</td>
      <td>${items || "—"}</td>
      <td>$${p.total}</td>
      <td>${badgeEstadoPedido(p.estado)}</td>
      <td>${acciones}</td>
    `;
    cuerpoPedidos.appendChild(tr);
  });

  ultimoIdPedido = idMasNuevo;
}

async function cargarLogs() {
  const res = await fetch("/api/logs");
  const logs = await res.json();

  cuerpoLogs.innerHTML = "";
  vacioLogs.hidden = logs.length > 0;

  const ordenados = logs.slice().reverse();
  const fechaMasNueva = ordenados.length ? ordenados[0].fecha : null;

  ordenados.forEach((l) => {
    const tr = document.createElement("tr");
    const autor = l.autor || "agente";
    if (l.escalar && autor === "agente") tr.classList.add("escalado");
    if (ultimaFechaLog !== null && l.fecha === fechaMasNueva && l.fecha !== ultimaFechaLog) {
      tr.classList.add("fila-nueva");
    }
    const botonAtender = `<br><button class="accion tomar" style="margin-top:6px" onclick="abrirConversacion('${escaparAttr(l.cliente)}')">Atender</button>`;
    let estado;
    let respuesta = escaparHtml(l.respuesta);
    if (autor === "humano") {
      estado = `<span class="badge badge-humano">Respondió un humano</span>`;
      respuesta = `👤 <strong>Encargado:</strong> ${respuesta}`;
    } else if (autor === "sistema") {
      estado = `<span class="badge badge-ok">De vuelta al agente</span>`;
      respuesta = `<em>${respuesta}</em>`;
    } else if (autor === "cliente-en-espera") {
      estado = `<span class="badge badge-sin-atender">Esperando al encargado</span>` + botonAtender;
      respuesta = `<em style="color:#888">(el agente no contesta: lo atiende una persona)</em>`;
    } else if (l.escalar) {
      estado = `<span class="badge badge-alerta" title="${escaparAttr(l.motivo || "")}">Requiere humano</span>` + botonAtender;
    } else {
      estado = `<span class="badge badge-ok">Resuelto por el agente</span>`;
    }
    tr.innerHTML = `
      <td>${horaLegible(l.fecha)}</td>
      <td class="canal">${escaparHtml(l.canal)}</td>
      <td>${escaparHtml(l.cliente)}</td>
      <td>${escaparHtml(l.mensaje) || "—"}</td>
      <td>${respuesta}</td>
      <td>${estado}</td>
    `;
    cuerpoLogs.appendChild(tr);
  });

  ultimaFechaLog = fechaMasNueva;
}

// --- KPIs animados ---

function animarNumero(el, valorNuevo, formateador) {
  formateador = formateador || ((n) => Math.round(n).toLocaleString("es-AR"));
  const valorAnterior = Number(el.dataset.valor || 0);
  el.dataset.valor = valorNuevo;
  if (valorAnterior === valorNuevo) {
    el.textContent = formateador(valorNuevo);
    return;
  }
  const duracion = 600;
  const inicio = performance.now();
  function paso(ahora) {
    const t = Math.min(1, (ahora - inicio) / duracion);
    const ease = 1 - Math.pow(1 - t, 3);
    const actual = valorAnterior + (valorNuevo - valorAnterior) * ease;
    el.textContent = formateador(actual);
    if (t < 1) requestAnimationFrame(paso);
  }
  requestAnimationFrame(paso);
}

const elMensajes = document.getElementById("kpi-mensajes");
const elPorcentaje = document.getElementById("kpi-porcentaje");
const elPendientes = document.getElementById("kpi-pendientes");
const elIngresos = document.getElementById("kpi-ingresos");
const elChartHero = document.getElementById("chart-hero-valor");
const elBarGood = document.getElementById("bar-seg-good");
const elBarCritical = document.getElementById("bar-seg-critical");
const elBarStack = document.getElementById("bar-stack");
const elLegendResueltos = document.getElementById("legend-resueltos");
const elLegendEscalados = document.getElementById("legend-escalados");
const elTablaChartBody = document.getElementById("tabla-chart-body");
const elTablaChart = document.getElementById("tabla-chart");
const elToggleTabla = document.getElementById("toggle-tabla-chart");

elToggleTabla.addEventListener("click", () => {
  elTablaChart.hidden = !elTablaChart.hidden;
  elToggleTabla.textContent = elTablaChart.hidden ? "Ver como tabla" : "Ocultar tabla";
});

async function cargarStats() {
  const res = await fetch("/api/stats");
  const s = await res.json();

  animarNumero(elMensajes, s.mensajes_hoy);
  animarNumero(elPendientes, s.pedidos_pendientes);
  animarNumero(elIngresos, s.ingresos_confirmados);

  const total = s.total_conversaciones || 0;
  const pctResuelto = total > 0 ? Math.round((s.resueltos / total) * 100) : 0;
  const pctEscalado = 100 - pctResuelto;

  animarNumero(elPorcentaje, pctResuelto);
  elChartHero.textContent = pctResuelto + "%";

  // Etiqueta dentro del segmento solo si hay espacio (>= 15%), si no,
  // queda solo en la leyenda (regla de "no recortar una etiqueta").
  elBarGood.style.flexBasis = Math.max(total > 0 ? pctResuelto : 50, 0) + "%";
  elBarCritical.style.flexBasis = Math.max(total > 0 ? pctEscalado : 50, 0) + "%";
  elBarGood.textContent = total > 0 && pctResuelto >= 15 ? pctResuelto + "%" : "";
  elBarCritical.textContent = total > 0 && pctEscalado >= 15 ? pctEscalado + "%" : "";
  elBarStack.title = total > 0
    ? `Resuelto por el agente: ${s.resueltos} (${pctResuelto}%) · Requiere humano: ${s.escalados} (${pctEscalado}%)`
    : "Todavía no hay conversaciones registradas";

  elLegendResueltos.textContent = s.resueltos;
  elLegendEscalados.textContent = s.escalados;

  elTablaChartBody.innerHTML = `
    <tr><td>🤖 Resuelto por el agente</td><td>${s.resueltos}</td><td>${total > 0 ? pctResuelto : 0}%</td></tr>
    <tr><td>🙋 Requiere humano</td><td>${s.escalados}</td><td>${total > 0 ? pctEscalado : 0}%</td></tr>
  `;
}

// --- Estado del token de WhatsApp ---

const elBanner = document.getElementById("banner-token");
const elBannerMotivo = document.getElementById("banner-token-motivo");
const elBannerInstagram = document.getElementById("banner-token-instagram");
const elBannerInstagramMotivo = document.getElementById("banner-token-instagram-motivo");

async function cargarEstadoCanal(endpoint, elBanner, elMotivo) {
  try {
    const res = await fetch(endpoint);
    const estado = await res.json();
    if (estado.ok === false) {
      elBanner.style.display = "flex";
      elMotivo.textContent = estado.motivo || "Revisá la consola del servidor para más detalle.";
    } else {
      elBanner.style.display = "none";
    }
  } catch {
    // si falla la consulta, no molestamos con el banner
  }
}

// --- Atención humana ---
// Lista de conversaciones que pidieron un humano + chat para responderles.

const elListaHumano = document.getElementById("humano-lista");
const elListaVacia = document.getElementById("humano-lista-vacio");
const elChatVacio = document.getElementById("humano-chat-vacio");
const elChatContenido = document.getElementById("humano-chat-contenido");
const elChatCliente = document.getElementById("chat-cliente");
const elChatCanal = document.getElementById("chat-canal");
const elChatEstado = document.getElementById("chat-estado");
const elChatHilo = document.getElementById("chat-hilo");
const elChatAviso = document.getElementById("chat-aviso");
const elChatTexto = document.getElementById("chat-texto");
const elBtnTomar = document.getElementById("btn-tomar");
const elBtnDevolver = document.getElementById("btn-devolver");
const elBtnEnviar = document.getElementById("btn-enviar");
const elBannerHumano = document.getElementById("banner-humano");
const elBannerHumanoTexto = document.getElementById("banner-humano-texto");

let clienteAbierto = null;
let cantidadMensajesHilo = -1;

function nombreCanal(canal) {
  return {
    "whatsapp-simulado": "WhatsApp (simulado)",
    "instagram-simulado": "Instagram (simulado)",
    "whatsapp-real-meta": "WhatsApp real",
    "instagram-real": "Instagram real",
    "whatsapp-real-twilio": "WhatsApp (Twilio)",
  }[canal] || canal || "";
}

async function postJSON(url, body) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function cargarIntervenciones() {
  const res = await fetch("/api/intervenciones");
  const lista = await res.json();

  elListaHumano.querySelectorAll(".conv-item").forEach((n) => n.remove());
  elListaVacia.hidden = lista.length > 0;

  lista.forEach((c) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "conv-item" + (c.cliente === clienteAbierto ? " activa" : "");
    const badge = c.estado === "humano"
      ? `<span class="badge badge-humano">Atendiendo</span>`
      : `<span class="badge badge-sin-atender">Sin atender</span>`;
    item.innerHTML = `
      <div class="fila1"><span class="cli">${escaparHtml(c.cliente)}</span>${badge}</div>
      <div class="canal">${escaparHtml(nombreCanal(c.canal))}</div>
      <div class="ultimo">${escaparHtml(c.ultimo_mensaje || "")}</div>
      <div class="motivo">${escaparHtml(c.motivo || "")}</div>
    `;
    item.addEventListener("click", () => abrirConversacion(c.cliente));
    elListaHumano.appendChild(item);
  });

  const sinAtender = lista.filter((c) => c.estado === "sin-atender").length;
  const atendiendo = lista.filter((c) => c.estado === "humano").length;
  if (sinAtender + atendiendo > 0) {
    elBannerHumano.style.display = "flex";
    elBannerHumanoTexto.textContent =
      sinAtender > 0
        ? `${sinAtender} conversación${sinAtender > 1 ? "es" : ""} pide${sinAtender > 1 ? "n" : ""} un humano.`
        : `Estás atendiendo ${atendiendo} conversación${atendiendo > 1 ? "es" : ""} (el agente está en pausa ahí).`;
  } else {
    elBannerHumano.style.display = "none";
  }
}

function renderHilo(mensajes) {
  const estabaAbajo = elChatHilo.scrollHeight - elChatHilo.scrollTop - elChatHilo.clientHeight < 40;
  elChatHilo.innerHTML = "";
  mensajes.forEach((m) => {
    const autor = m.autor || "agente";
    if (m.mensaje) {
      const d = document.createElement("div");
      d.className = "msg cliente";
      d.innerHTML = `<div class="de">🧑 Cliente · ${horaLegible(m.fecha)}</div>`;
      d.appendChild(document.createTextNode(m.mensaje));
      elChatHilo.appendChild(d);
    }
    if (!m.respuesta) return;
    const r = document.createElement("div");
    if (autor === "humano") {
      r.className = "msg humano";
      r.innerHTML = `<div class="de">👤 Encargado</div>`;
    } else if (autor === "sistema") {
      r.className = "msg sistema";
    } else {
      r.className = "msg agente" + (m.escalar ? " escalado" : "");
      r.innerHTML = `<div class="de">🤖 Agente${m.escalar ? " · pidió ayuda: " + escaparHtml(m.motivo || "") : ""}</div>`;
    }
    r.appendChild(document.createTextNode(m.respuesta));
    elChatHilo.appendChild(r);
  });
  if (estabaAbajo || cantidadMensajesHilo === -1) elChatHilo.scrollTop = elChatHilo.scrollHeight;
}

async function cargarConversacionAbierta() {
  if (!clienteAbierto) return;
  const res = await fetch(`/api/conversacion?cliente=${encodeURIComponent(clienteAbierto)}`);
  const data = await res.json();

  elChatCliente.textContent = data.cliente;
  elChatCanal.textContent = nombreCanal(data.canal);
  elChatEstado.className = "badge " + (data.en_manos_humano ? "badge-humano" : "badge-ok");
  elChatEstado.textContent = data.en_manos_humano ? "La atendés vos · agente en pausa" : "La atiende el agente";
  elBtnTomar.hidden = data.en_manos_humano;
  elBtnDevolver.hidden = !data.en_manos_humano;

  if (data.canal === "whatsapp-real-twilio") {
    elChatAviso.hidden = false;
    elChatAviso.textContent = "Con Twilio no se pueden mandar mensajes del encargado. Para responder como humano usen WhatsApp con Meta.";
  } else {
    elChatAviso.hidden = true;
  }

  if (data.mensajes.length !== cantidadMensajesHilo) {
    renderHilo(data.mensajes);
    cantidadMensajesHilo = data.mensajes.length;
  }
}

function abrirConversacion(cliente) {
  clienteAbierto = cliente;
  cantidadMensajesHilo = -1;
  elChatVacio.style.display = "none";
  elChatContenido.style.display = "flex";
  document.getElementById("seccion-humano").scrollIntoView({ behavior: "smooth" });
  cargarConversacionAbierta();
  cargarIntervenciones();
  elChatTexto.focus();
}

elBtnTomar.addEventListener("click", async () => {
  await postJSON("/api/intervenciones/tomar", { cliente: clienteAbierto });
  cargarConversacionAbierta();
  cargarIntervenciones();
});

elBtnDevolver.addEventListener("click", async () => {
  await postJSON("/api/intervenciones/devolver", { cliente: clienteAbierto });
  cargarConversacionAbierta();
  cargarIntervenciones();
});

async function enviarRespuestaHumana(e) {
  if (e) e.preventDefault();
  const texto = elChatTexto.value.trim();
  if (!texto || !clienteAbierto) return;
  elBtnEnviar.disabled = true;
  try {
    const r = await postJSON("/api/intervenciones/responder", { cliente: clienteAbierto, texto });
    if (r.ok === false && r.aviso) {
      elChatAviso.hidden = false;
      elChatAviso.textContent = r.aviso;
    }
    elChatTexto.value = "";
  } finally {
    elBtnEnviar.disabled = false;
    elChatTexto.focus();
  }
  cargarConversacionAbierta();
  cargarIntervenciones();
}

document.getElementById("form-responder").addEventListener("submit", enviarRespuestaHumana);
elChatTexto.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) enviarRespuestaHumana(e);
});

function actualizarTodo() {
  cargarIntervenciones();
  cargarConversacionAbierta();
  cargarPedidos();
  cargarLogs();
  cargarStats();
  cargarEstadoCanal("/api/whatsapp-status", elBanner, elBannerMotivo);
  cargarEstadoCanal("/api/instagram-status", elBannerInstagram, elBannerInstagramMotivo);
}

actualizarTodo();
setInterval(actualizarTodo, 3000);
