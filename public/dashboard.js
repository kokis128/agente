// Panel del dueño: consulta periódicamente al servidor para mostrar
// en vivo lo que el agente va contestando, los pedidos que toma,
// unos KPIs animados y el estado del token de WhatsApp real.

const cuerpoPedidos = document.querySelector("#tabla-pedidos tbody");
const vacioPedidos = document.getElementById("vacio-pedidos");
const cuerpoLogs = document.querySelector("#tabla-logs tbody");
const vacioLogs = document.getElementById("vacio-logs");

let ultimoIdPedido = null;
let ultimaFechaLog = null;

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
    if (l.escalar) tr.classList.add("escalado");
    if (ultimaFechaLog !== null && l.fecha === fechaMasNueva && l.fecha !== ultimaFechaLog) {
      tr.classList.add("fila-nueva");
    }
    const estado = l.escalar
      ? `<span class="badge badge-alerta" title="${l.motivo || ''}">Requiere humano</span>`
      : `<span class="badge badge-ok">Resuelto por el agente</span>`;
    tr.innerHTML = `
      <td>${horaLegible(l.fecha)}</td>
      <td class="canal">${l.canal}</td>
      <td>${l.cliente}</td>
      <td>${l.mensaje}</td>
      <td>${l.respuesta}</td>
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

async function cargarEstadoWhatsapp() {
  try {
    const res = await fetch("/api/whatsapp-status");
    const estado = await res.json();
    if (estado.ok === false) {
      elBanner.style.display = "flex";
      elBannerMotivo.textContent = estado.motivo || "Revisá la consola del servidor para más detalle.";
    } else {
      elBanner.style.display = "none";
    }
  } catch {
    // si falla la consulta, no molestamos con el banner
  }
}

function actualizarTodo() {
  cargarPedidos();
  cargarLogs();
  cargarStats();
  cargarEstadoWhatsapp();
}

actualizarTodo();
setInterval(actualizarTodo, 3000);
