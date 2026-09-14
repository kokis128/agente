// Panel del dueño: consulta periódicamente al servidor para mostrar
// en vivo lo que el agente va contestando y los pedidos que toma.

const cuerpoPedidos = document.querySelector("#tabla-pedidos tbody");
const vacioPedidos = document.getElementById("vacio-pedidos");
const cuerpoLogs = document.querySelector("#tabla-logs tbody");
const vacioLogs = document.getElementById("vacio-logs");

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

  pedidos
    .slice()
    .reverse()
    .forEach((p) => {
      const tr = document.createElement("tr");
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
}

async function cargarLogs() {
  const res = await fetch("/api/logs");
  const logs = await res.json();

  cuerpoLogs.innerHTML = "";
  vacioLogs.hidden = logs.length > 0;

  logs
    .slice()
    .reverse()
    .forEach((l) => {
      const tr = document.createElement("tr");
      if (l.escalar) tr.classList.add("escalado");
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
}

function actualizarTodo() {
  cargarPedidos();
  cargarLogs();
}

actualizarTodo();
setInterval(actualizarTodo, 3000);
