"""Panel HTML mínimo para admins.

Se sirve como HTML estático. El JS de la página hace fetch a la API con
la cookie de sesión del admin. Si el admin no está autenticado, los fetch
devuelven 401 y se muestra un mensaje.

No usamos frameworks (React, Vue, etc.): HTML + CSS + JS vanilla, todo
inline para no añadir dependencias al backend. La UI moderna real llega
en Fase 8.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse


router = APIRouter(tags=["admin-dashboard"])


_DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ELI — Admin</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
    Roboto, sans-serif; background: #0f1117; color: #e5e7eb;
    font-size: 14px; line-height: 1.5;
  }
  header {
    padding: 20px 24px; border-bottom: 1px solid #1f2937;
    display: flex; justify-content: space-between; align-items: center;
  }
  h1 { margin: 0; font-size: 20px; font-weight: 600; letter-spacing: -0.01em; }
  h1 span { color: #6b7280; font-weight: 400; margin-left: 6px; }
  main { padding: 24px; max-width: 1200px; margin: 0 auto; }
  .grid {
    display: grid; gap: 16px;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  }
  .card {
    background: #161b22; border: 1px solid #1f2937; border-radius: 8px;
    padding: 16px;
  }
  .card-label { color: #9ca3af; font-size: 12px; text-transform: uppercase;
    letter-spacing: 0.04em; margin-bottom: 6px; }
  .card-value { font-size: 24px; font-weight: 600; color: #f3f4f6; }
  h2 { font-size: 16px; margin: 32px 0 12px; color: #d1d5db; }
  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th, td { text-align: left; padding: 8px 10px; border-bottom: 1px solid #1f2937; }
  th { color: #9ca3af; font-weight: 500; font-size: 12px;
       text-transform: uppercase; letter-spacing: 0.04em; }
  tr:hover { background: #1a2027; }
  code { background: #1f2937; padding: 2px 6px; border-radius: 4px;
         font-size: 12px; color: #fbbf24; }
  .status { display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 500; text-transform: uppercase; }
  .status-ok { background: #064e3b; color: #6ee7b7; }
  .status-error { background: #7f1d1d; color: #fca5a5; }
  .muted { color: #6b7280; font-size: 12px; }
  .error-banner {
    padding: 12px 16px; background: #7f1d1d; border-radius: 8px;
    margin-bottom: 16px; display: none;
  }
  .error-banner.visible { display: block; }
  footer { padding: 24px; text-align: center; color: #4b5563; font-size: 12px; }
</style>
</head>
<body>
<header>
  <h1>ELI<span>· Admin</span></h1>
  <div class="muted" id="env-info">cargando…</div>
</header>
<main>
  <div id="error-banner" class="error-banner"></div>

  <h2>Resumen</h2>
  <div class="grid" id="overview-grid">
    <div class="card"><div class="card-label">Cargando…</div></div>
  </div>

  <h2>Serie (últimos 7 días)</h2>
  <div class="card">
    <table id="timeseries-table">
      <thead><tr><th>Fecha</th><th>Mensajes</th><th>Tokens</th><th>Errores</th></tr></thead>
      <tbody><tr><td colspan="4" class="muted">Cargando…</td></tr></tbody>
    </table>
  </div>

  <h2>Estado del sistema</h2>
  <div class="grid" id="health-grid">
    <div class="card"><div class="card-label">Cargando…</div></div>
  </div>

  <h2>Últimas acciones administrativas</h2>
  <div class="card">
    <table id="audit-table">
      <thead><tr><th>Acción</th><th>Entidad</th><th>Actor</th><th>Fecha</th></tr></thead>
      <tbody><tr><td colspan="4" class="muted">Cargando…</td></tr></tbody>
    </table>
  </div>
</main>
<footer>
  ELI Admin · dashboard interno · panel moderno llega en Fase 8
</footer>

<script>
const API = "/api/v1/admin";

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else e.setAttribute(k, v);
  }
  for (const c of children) {
    if (typeof c === "string") e.appendChild(document.createTextNode(c));
    else if (c) e.appendChild(c);
  }
  return e;
}

function showError(msg) {
  const b = document.getElementById("error-banner");
  b.textContent = msg;
  b.classList.add("visible");
}

async function getJSON(path) {
  const r = await fetch(path, { credentials: "include" });
  if (r.status === 401) throw new Error("No autenticado. Inicia sesión como admin.");
  if (r.status === 403) throw new Error("Permisos insuficientes para ver esta sección.");
  if (!r.ok) throw new Error("HTTP " + r.status + " en " + path);
  return r.json();
}

async function loadOverview() {
  const grid = document.getElementById("overview-grid");
  try {
    const d = await getJSON(API + "/analytics/overview");
    const cards = [
      ["Usuarios totales", d.users_total],
      ["Usuarios activos", d.users_active],
      ["Usuarios bloqueados", d.users_blocked],
      ["Conversaciones", d.conversations_total],
      ["Mensajes", d.messages_total],
      ["Memorias activas", d.memories_total],
      ["Documentos", d.documents_total],
      ["Tool calls", d.tool_calls_total],
      ["Tokens totales", d.tokens_total],
      ["Coste estimado", "$" + Number(d.cost_estimate_usd).toFixed(4)],
      ["Errores", d.errors_total],
    ];
    grid.replaceChildren(...cards.map(([label, value]) =>
      el("div", { class: "card" },
        el("div", { class: "card-label" }, label),
        el("div", { class: "card-value" }, String(value))
      )
    ));
  } catch (e) {
    showError("Overview: " + e.message);
    grid.replaceChildren(el("div", { class: "card" },
      el("div", { class: "card-label" }, "Error al cargar")));
  }
}

async function loadTimeseries() {
  const tbody = document.querySelector("#timeseries-table tbody");
  try {
    const d = await getJSON(API + "/analytics/timeseries?days=7");
    tbody.replaceChildren(...d.points.map(p =>
      el("tr", {},
        el("td", {}, p.date),
        el("td", {}, String(p.messages)),
        el("td", {}, String(p.tokens)),
        el("td", {}, String(p.errors))
      )
    ));
  } catch (e) {
    showError("Timeseries: " + e.message);
    tbody.replaceChildren(el("tr", {}, el("td", { colspan: "4", class: "muted" }, "Error")));
  }
}

async function loadHealth() {
  const grid = document.getElementById("health-grid");
  try {
    const d = await getJSON(API + "/system/health");
    const cards = [
      ["Estado", d.status, d.status === "ok" ? "status-ok" : "status-error"],
      ["Base de datos", d.database, d.database === "ok" ? "status-ok" : "status-error"],
      ["Entorno", d.env],
      ["Versión", d.version],
      ["LLM provider", d.llm_provider],
      ["Embeddings", d.embeddings_provider],
      ["Tools registradas", d.tools_count],
    ];
    grid.replaceChildren(...cards.map(([label, value, statusClass]) =>
      el("div", { class: "card" },
        el("div", { class: "card-label" }, label),
        statusClass
          ? el("div", { class: "status " + statusClass }, String(value))
          : el("div", { class: "card-value", style: "font-size:16px" }, String(value))
      )
    ));
    document.getElementById("env-info").textContent =
      d.env + " · " + d.version + " · " + d.llm_provider;
  } catch (e) {
    showError("Health: " + e.message);
    grid.replaceChildren(el("div", { class: "card" },
      el("div", { class: "card-label" }, "Error al cargar")));
  }
}

async function loadAudit() {
  const tbody = document.querySelector("#audit-table tbody");
  try {
    const d = await getJSON(API + "/audit?limit=20");
    if (!d.length) {
      tbody.replaceChildren(el("tr", {}, el("td", { colspan: "4", class: "muted" }, "Sin acciones registradas")));
      return;
    }
    tbody.replaceChildren(...d.map(a =>
      el("tr", {},
        el("td", {}, el("code", {}, a.action)),
        el("td", {}, (a.entity_type || "—") + (a.entity_id ? ":" + a.entity_id.slice(0, 12) : "")),
        el("td", {}, a.actor_user_id ? a.actor_user_id.slice(0, 8) + "…" : "sistema"),
        el("td", {}, new Date(a.created_at).toLocaleString())
      )
    ));
  } catch (e) {
    // Audit requiere SUPER_ADMIN; si el admin es sólo ADMIN, no mostramos error rojo
    if (e.message.includes("insuficientes")) {
      tbody.replaceChildren(el("tr", {}, el("td", { colspan: "4", class: "muted" }, "Requiere SUPER_ADMIN")));
      return;
    }
    showError("Audit: " + e.message);
    tbody.replaceChildren(el("tr", {}, el("td", { colspan: "4", class: "muted" }, "Error")));
  }
}

loadOverview();
loadTimeseries();
loadHealth();
loadAudit();
</script>
</body>
</html>
"""


@router.get("/admin/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def admin_dashboard() -> HTMLResponse:
    """Sirve el panel HTML. La autenticación la hace el frontend vía API calls.

    No hacemos autenticación aquí para simplificar; los endpoints /api/v1/admin/*
    que el JS consulta sí están protegidos. Si un usuario no-admin abre esta
    página, verá el HTML pero los fetch devolverán 401/403 y aparecerán
    errores en pantalla.
    """
    return HTMLResponse(content=_DASHBOARD_HTML)