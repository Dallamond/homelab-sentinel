const API = "/api";

// --- Config opcional desde meta tags en el HTML ---
function getMeta(name) {
  const el = document.querySelector(`meta[name="${name}"]`);
  return el ? el.getAttribute("content") : "";
}
const META_DASHBOARD_API_KEY = getMeta("dashboard-api-key") || "";
const isDemo = getMeta("demo-mode") === "true";

// Persistencia de la clave del dashboard en localStorage
const LS_KEY = "sentinel_dashboard_key";
function getDashboardKey() {
  try { return localStorage.getItem(LS_KEY) || META_DASHBOARD_API_KEY; }
  catch { return META_DASHBOARD_API_KEY; }
}
function setDashboardKey(value) {
  try {
    if (value) localStorage.setItem(LS_KEY, value);
    else localStorage.removeItem(LS_KEY);
  } catch { /* localStorage no disponible */ }
}

function showAuthBox() {
  const box = document.getElementById("authBox");
  if (box) box.classList.remove("hidden");
}
function hideAuthBox() {
  const box = document.getElementById("authBox");
  if (box) box.classList.add("hidden");
}

function sevClass(sev) { return `sev sev-${sev}`; }
function fmtTime(iso) { return new Date(iso).toLocaleString(); }
function fmtTimeShort(iso) { return new Date(iso).toLocaleTimeString(); }
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

// Headers comunes
function authHeaders() {
  const h = { "Content-Type": "application/json" };
  const key = getDashboardKey();
  if (key) h["X-Dashboard-Key"] = key;
  return h;
}

// Interceptor global de 401 → mostrar auth box
const _rawFetch = window.fetch.bind(window);
window.fetch = async (url, options = {}) => {
  const res = await _rawFetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (res.status === 401 && !isDemo) showAuthBox();
  return res;
};

// --- Hosts en tiempo real ---
const LIVE_THRESHOLD_MS = 15_000;
const RECENT_THRESHOLD_MS = 5 * 60_000;

let lastKnownEvents = [];
let lastKnownSources = [];

function renderHostsStrip() {
  const strip = document.getElementById("hostsStrip");
  if (!strip) return;

  const hosts = new Set([
    ...lastKnownEvents.map((e) => e.host),
    ...lastKnownSources.map((s) => s.host),
  ]);

  if (hosts.size === 0) {
    strip.innerHTML = '<p class="hint">Todavía no se ha registrado ningún host.</p>';
    updateHostFilter([]);
    return;
  }

  const now = Date.now();
  strip.innerHTML = "";

  [...hosts].sort().forEach((host) => {
    const hostEvents = lastKnownEvents.filter((e) => e.host === host);
    const lastEvent = hostEvents.reduce(
      (latest, e) => (!latest || new Date(e.timestamp) > new Date(latest.timestamp) ? e : latest),
      null
    );
    const activeSources = lastKnownSources.filter((s) => s.host === host && s.enabled).length;

    let dotClass = "dot-stale";
    let statusText = "Sin datos recientes";
    if (lastEvent) {
      const age = now - new Date(lastEvent.timestamp).getTime();
      if (age <= LIVE_THRESHOLD_MS) {
        dotClass = "dot-live";
        statusText = "Leyendo en tiempo real";
      } else if (age <= RECENT_THRESHOLD_MS) {
        dotClass = "dot-recent";
        statusText = "Activo recientemente";
      } else {
        statusText = "Sin datos recientes";
      }
    }

    const card = document.createElement("div");
    card.className = "host-card";
    card.innerHTML = `
      <div class="host-name">${escapeHtml(host)}</div>
      <div class="host-status"><span class="dot ${dotClass}"></span>${statusText}</div>
      <div class="host-meta">${lastEvent ? `Última actividad: ${fmtTimeShort(lastEvent.timestamp)}` : "Sin eventos todavía"}</div>
      <div class="host-meta">${activeSources} fuente${activeSources === 1 ? "" : "s"} activa${activeSources === 1 ? "" : "s"}</div>
    `;
    strip.appendChild(card);
  });

  updateHostFilter([...hosts].sort());
}

function updateHostFilter(hosts) {
  const sel = document.getElementById("hostFilter");
  if (!sel) return;
  const current = sel.value;
  sel.innerHTML = '<option value="">todos</option>' + hosts.map(h => `<option value="${escapeHtml(h)}">${escapeHtml(h)}</option>`).join("");
  if (hosts.includes(current)) sel.value = current;
  else sel.value = "";
}

function markRefreshed() {
  const el = document.getElementById("lastRefresh");
  if (el) el.textContent = `Última actualización: ${new Date().toLocaleTimeString()}`;
}

// --- Tabs ---
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((t) => t.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(`tab-${btn.dataset.tab}`).classList.add("active");
  });
});

// --- Health ---
async function checkHealth() {
  const el = document.getElementById("health");
  try {
    const res = await fetch(`${API}/health`);
    const data = await res.json();
    el.textContent = `${data.status} · ${data.role} · ${data.host}${data.auth_required ? " 🔐" : ""}`;
    el.className = "badge ok";
    // Si el backend pide auth y no tenemos clave → mostrar auth box
    if (data.auth_required && !getDashboardKey()) showAuthBox();
    else if (data.auth_required && getDashboardKey()) {
      // Tenemos clave almacenada; ocultamos auth box
      // (si falla la siguiente petición, el interceptor de 401 lo volverá a mostrar)
      hideAuthBox();
    } else hideAuthBox();
  } catch {
    el.textContent = "sin conexión";
    el.className = "badge down";
  }
}

// --- Events / live feed ---
let severityChart;
function renderSeverityChart(events) {
  const ctx = document.getElementById("severityChart");
  if (!ctx) return;

  if (typeof Chart === "undefined") {
    if (!ctx.dataset.warned) {
      ctx.replaceWith(Object.assign(document.createElement("p"), {
        className: "hint",
        textContent: "Gráfico no disponible (Chart.js no cargó — probablemente sin conexión a internet). El resto del dashboard funciona igualmente.",
      }));
    }
    return;
  }

  try {
    const counts = { debug: 0, info: 0, warning: 0, error: 0, critical: 0 };
    events.forEach((e) => { counts[e.severity] = (counts[e.severity] || 0) + 1; });
    const data = {
      labels: Object.keys(counts),
      datasets: [{
        data: Object.values(counts),
        backgroundColor: ["#6b7280", "#3b82f6", "#f0b429", "#ef4444", "#dc2626"],
        borderWidth: 0,
      }],
    };
    if (severityChart) {
      severityChart.data = data;
      severityChart.update();
    } else {
      severityChart = new Chart(ctx, {
        type: "doughnut",
        data,
        options: { plugins: { legend: { labels: { color: "#c8cddb" } } } },
      });
    }
  } catch (err) {
    console.error("No se pudo dibujar el gráfico de severidad:", err);
  }
}

function matchesSearch(event, query) {
  if (!query) return true;
  const haystack = `${event.message} ${event.source_name} ${event.host}`.toLowerCase();
  return haystack.includes(query.toLowerCase());
}

async function loadEvents() {
  const severity = document.getElementById("severityFilter").value;
  const host = document.getElementById("hostFilter").value;
  const search = document.getElementById("searchFilter").value.trim();
  const params = new URLSearchParams({ limit: "100" });
  if (severity) params.set("severity", severity);
  if (host) params.set("host", host);

  const res = await fetch(`${API}/events?${params}`, { headers: authHeaders() });
  const allEvents = await res.json();
  lastKnownEvents = allEvents;
  renderHostsStrip();
  markRefreshed();

  const events = allEvents.filter((e) => matchesSearch(e, search));

  renderSeverityChart(events);

  const tbody = document.querySelector("#eventsTable tbody");
  tbody.innerHTML = "";

  if (events.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="hint">Sin eventos que coincidan con el filtro.</td></tr>`;
    return;
  }

  events.forEach((e) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="mono">${fmtTime(e.timestamp)}</td>
      <td class="mono">${escapeHtml(e.host)}</td>
      <td class="mono">${escapeHtml(e.source_name)}</td>
      <td><span class="${sevClass(e.severity)}">${e.severity}</span></td>
      <td>${escapeHtml(e.message.slice(0, 140))}</td>
      <td><button class="explain-btn" data-id="${e.id}">Explícame esto</button></td>
    `;
    tbody.appendChild(tr);
  });

  document.querySelectorAll(".explain-btn").forEach((btn) => {
    btn.addEventListener("click", () => explainEvent(btn.dataset.id));
  });
}

// --- Explain (Gemini/LLM on demand) ---
async function explainEvent(eventId) {
  const modal = document.getElementById("explainModal");
  const content = document.getElementById("explainContent");
  modal.classList.remove("hidden");
  content.textContent = "Pensando...";
  try {
    const res = await fetch(`${API}/explain`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ event_id: Number(eventId) }),
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    content.textContent = data.explanation;
  } catch (err) {
    content.textContent = `No se pudo explicar: ${err}`;
  }
}
document.getElementById("closeModal").addEventListener("click", () => {
  document.getElementById("explainModal").classList.add("hidden");
});

// --- Alerts ---
function updateAlertsBadge(count) {
  const badge = document.getElementById("alertsBadge");
  if (!badge) return;
  badge.textContent = count > 0 ? String(count) : "";
  badge.classList.toggle("hidden", count === 0);
}

async function loadAlerts() {
  const res = await fetch(`${API}/alerts?limit=100`, { headers: authHeaders() });
  const alerts = await res.json();
  updateAlertsBadge(alerts.length);

  const tbody = document.querySelector("#alertsTable tbody");
  tbody.innerHTML = "";

  if (alerts.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="hint">Sin alertas todavía. Buena señal.</td></tr>`;
    return;
  }

  alerts.forEach((a) => {
    const tr = document.createElement("tr");
    const notified = [a.notified_telegram ? "telegram" : null, a.notified_email ? "email" : null]
      .filter(Boolean).join(", ") || "solo dashboard";
    tr.innerHTML = `
      <td class="mono">${fmtTime(a.created_at)}</td>
      <td>${escapeHtml(a.rule_name)}</td>
      <td><span class="${sevClass(a.severity)}">${a.severity}</span></td>
      <td class="mono">${escapeHtml(a.host)} / ${escapeHtml(a.source_name)}</td>
      <td>${escapeHtml(a.summary)}</td>
      <td>${notified}</td>
    `;
    tbody.appendChild(tr);
  });
}

// --- Sources (agrupadas por host) ---
async function loadSources() {
  const res = await fetch(`${API}/sources`, { headers: authHeaders() });
  const sources = await res.json();
  lastKnownSources = sources;
  renderHostsStrip();

  const container = document.getElementById("sourcesByHost");
  container.innerHTML = "";

  if (sources.length === 0) {
    container.innerHTML = '<p class="hint">Todavía no se ha descubierto ninguna fuente. Arranca un agente en un host y espera unos segundos.</p>';
    return;
  }

  const byHost = sources.reduce((acc, s) => {
    (acc[s.host] ||= []).push(s);
    return acc;
  }, {});

  Object.keys(byHost).sort().forEach((host) => {
    const hostSources = byHost[host].sort((a, b) => a.source_name.localeCompare(b.source_name));
    const enabledCount = hostSources.filter((s) => s.enabled).length;

    const section = document.createElement("div");
    section.className = "source-host-group";
    section.innerHTML = `
      <div class="source-host-header">
        <span class="source-host-name">${escapeHtml(host)}</span>
        <span class="hint">${enabledCount} / ${hostSources.length} activas</span>
      </div>
      <table>
        <thead><tr><th>Tipo</th><th>Nombre</th><th>Última vez visto</th><th>Activo</th></tr></thead>
        <tbody>
          ${hostSources.map((s) => `
            <tr>
              <td class="mono">${s.source_type}</td>
              <td class="mono">${escapeHtml(s.source_name)}</td>
              <td class="mono">${fmtTime(s.last_seen)}</td>
              <td><input type="checkbox" class="toggle" data-id="${s.id}" ${s.enabled ? "checked" : ""}/></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
    container.appendChild(section);
  });

  document.querySelectorAll(".toggle").forEach((cb) => {
    cb.addEventListener("change", async () => {
      await fetch(`${API}/sources/${cb.dataset.id}/toggle`, { method: "POST", headers: authHeaders() });
      loadSources();
    });
  });
}

// --- Summaries ---
function renderMarkdownLite(md) {
  const lines = md.split("\n");
  let html = "";
  let inList = false;

  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  const inline = (text) =>
    escapeHtml(text)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>");

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (line === "") { closeList(); continue; }
    if (line.startsWith("## ")) { closeList(); html += `<h4>${inline(line.slice(3))}</h4>`; continue; }
    if (line.startsWith("# ")) { closeList(); html += `<h3>${inline(line.slice(2))}</h3>`; continue; }
    if (line.startsWith("- ") || line.startsWith("* ")) {
      if (!inList) { html += "<ul>"; inList = true; }
      html += `<li>${inline(line.slice(2))}</li>`;
      continue;
    }
    closeList();
    html += `<p>${inline(line)}</p>`;
  }
  closeList();
  return html;
}

async function loadSummaries() {
  const res = await fetch(`${API}/summaries`, { headers: authHeaders() });
  const summaries = await res.json();
  const container = document.getElementById("summariesList");
  container.innerHTML = "";
  if (summaries.length === 0) {
    container.innerHTML = '<p class="hint">Todavía no hay resúmenes generados.</p>';
    return;
  }
  summaries.forEach((s) => {
    const div = document.createElement("div");
    div.className = "summary-item";
    div.innerHTML = `
      <div class="summary-header">
        <span class="summary-period">${s.period === "weekly" ? "Semanal" : "Mensual"}</span>
        <span class="hint">generado con ${escapeHtml(s.backend_used)}</span>
      </div>
      <div class="meta">${fmtTime(s.period_start)} → ${fmtTime(s.period_end)}</div>
      <div class="summary-body">${renderMarkdownLite(s.content_md)}</div>
    `;
    container.appendChild(div);
  });
}

document.getElementById("genWeekly").addEventListener("click", async () => {
  const btn = document.getElementById("genWeekly");
  btn.disabled = true;
  btn.textContent = "Generando...";
  try {
    await fetch(`${API}/summaries/generate?period=weekly`, { method: "POST", headers: authHeaders() });
    loadSummaries();
  } catch (e) {
    alert("Error: " + e);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generar resumen semanal ahora";
  }
});
document.getElementById("genMonthly").addEventListener("click", async () => {
  const btn = document.getElementById("genMonthly");
  btn.disabled = true;
  btn.textContent = "Generando...";
  try {
    await fetch(`${API}/summaries/generate?period=monthly`, { method: "POST", headers: authHeaders() });
    loadSummaries();
  } catch (e) {
    alert("Error: " + e);
  } finally {
    btn.disabled = false;
    btn.textContent = "Generar resumen mensual ahora";
  }
});

// --- Rules ---
async function loadRules() {
  const res = await fetch(`${API}/rules`, { headers: authHeaders() });
  const rules = await res.json();
  const container = document.getElementById("rulesList");
  container.innerHTML = "";
  if (rules.length === 0) {
    container.innerHTML = '<p class="hint">No hay reglas cargadas. Edita rules.yaml y recarga.</p>';
    return;
  }
  rules.forEach((r) => {
    const div = document.createElement("div");
    div.className = "rule-card";
    const notify = r.notify.length ? r.notify.join(", ") : "solo dashboard";
    div.innerHTML = `
      <div class="rule-header">
        <span class="rule-name">${escapeHtml(r.name)}</span>
        <span class="${sevClass(r.severity)}">${r.severity}</span>
      </div>
      <div class="rule-meta">
        <span class="mono">match: <code>${escapeHtml(r.match)}</code></span>
        <span class="mono">origen: ${r.source_type}</span>
        <span class="mono">min sev: ${r.min_severity}</span>
        <span class="mono">umbral: ${r.threshold} en ${r.window_seconds}s</span>
        <span class="mono">cooldown: ${r.cooldown_seconds}s</span>
        <span class="mono">notifica: ${notify}</span>
      </div>
    `;
    container.appendChild(div);
  });
}

document.getElementById("reloadRules").addEventListener("click", async () => {
  const btn = document.getElementById("reloadRules");
  btn.disabled = true;
  btn.textContent = "Recargando...";
  try {
    await fetch(`${API}/rules/reload`, { method: "POST", headers: authHeaders() });
    loadRules();
  } catch (e) {
    alert("Error: " + e);
  } finally {
    btn.disabled = false;
    btn.textContent = "Recargar rules.yaml";
  }
});

// --- Init ---
checkHealth();
loadEvents();
loadAlerts();
loadSources();
loadSummaries();
loadRules();
loadSettings();

document.getElementById("refreshEvents").addEventListener("click", loadEvents);
document.getElementById("severityFilter").addEventListener("change", loadEvents);
document.getElementById("hostFilter").addEventListener("change", loadEvents);
document.getElementById("searchFilter").addEventListener("input", () => {
  clearTimeout(window.__searchDebounce);
  window.__searchDebounce = setTimeout(loadEvents, 200);
});

setInterval(checkHealth, 15000);
setInterval(loadEvents, 5000);
setInterval(loadAlerts, 10000);
setInterval(loadSources, 20000);
setInterval(renderHostsStrip, 1000);

// --- Auth box IIFE ---
(function() {
  const input = document.getElementById("authKeyInput");
  const saveBtn = document.getElementById("authKeySave");
  const errorEl = document.getElementById("authError");
  if (!input || !saveBtn) return;

  // Pre-rellenar si ya hay clave almacenada
  const existing = getDashboardKey();
  if (existing) input.value = existing;

  async function saveKey() {
    const key = input.value.trim();
    setDashboardKey(key);
    errorEl.textContent = "";
    hideAuthBox();
    // Reintentar salud con la nueva clave
    await checkHealth();
    // Si la clave es correcta, las peticiones siguientes funcionarán;
    // si no, el interceptor de 401 volverá a mostrar el auth box.
  }

  saveBtn.addEventListener("click", saveKey);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") saveKey(); });
})();

// --- Ajustes (A1-A5) ---
const SETTING_SECRET_KEYS = new Set([
  "agent_api_key", "dashboard_api_key", "telegram_bot_token",
  "smtp_password", "gemini_api_key", "openai_compat_api_key",
]);

function applySettingsData(data) {
  const eff = data.effective;
  document.querySelectorAll("[data-key]").forEach((el) => {
    const key = el.dataset.key;
    if (!(key in eff)) return;
    const val = eff[key];
    if (el.type === "checkbox" || el.dataset.type === "bool") {
      el.checked = Boolean(val);
    } else {
      el.value = val ?? "";
    }
    el.dataset.orig = el.value;
  });
  updateAuthStatus(data);
}

function updateAuthStatus(data) {
  const badge = document.getElementById("authStatusBadge");
  if (!badge) return;
  if (!data) { badge.textContent = "cargando..."; return; }
  const key = data.effective.dashboard_api_key;
  const hasKey = typeof key === "string" && key.length > 2;
  badge.textContent = hasKey ? "🔐 Auth activa" : "ABIERTO (sin clave)";
  badge.className = "badge " + (hasKey ? "ok" : "warn");
}

async function loadSettings() {
  try {
    const res = await fetch(`${API}/settings`, { headers: authHeaders() });
    if (!res.ok) return;
    applySettingsData(await res.json());
  } catch { /* silent */ }
}

async function saveSettings(group) {
  const container = document.querySelector(`.settings-group[data-group="${group}"]`);
  if (!container) return;
  const updates = {};
  container.querySelectorAll("[data-key]").forEach((el) => {
    const key = el.dataset.key;
    if (el.type === "checkbox" || el.dataset.type === "bool") {
      updates[key] = el.checked;
      return;
    }
    const val = el.value;
    const orig = el.dataset.orig;
    // En campos secretos: si el usuario no lo tocó, no enviar
    if (SETTING_SECRET_KEYS.has(key) && val === orig) return;
    updates[key] = val || null;
  });

  const btn = container.querySelector(".settings-save");
  const status = container.querySelector(".settings-status");
  btn.disabled = true;
  btn.textContent = "Guardando…";
  try {
    const res = await fetch(`${API}/settings`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ updates }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || res.statusText);
    }
    const data = await res.json();
    applySettingsData(data);
    if (status) { status.textContent = "✅ Guardado"; status.className = "settings-status hint ok"; }
    // Si cambió la dashboard key, actualizar localStorage
    if (updates.dashboard_api_key && !SETTING_SECRET_KEYS.has("dashboard_api_key")) {
      setDashboardKey(updates.dashboard_api_key);
    } else if (updates.dashboard_api_key !== undefined && updates.dashboard_api_key === null) {
      // Revert to env default → clear localStorage
      setDashboardKey("");
    }
    if (updates.dashboard_api_key !== undefined) {
      await checkHealth();
    }
  } catch (e) {
    if (status) { status.textContent = "❌ " + e.message; status.className = "settings-status hint err"; }
  } finally {
    btn.disabled = false;
    btn.textContent = "Guardar";
  }
}

async function testSettings(group) {
  const container = document.querySelector(`.settings-group[data-group="${group}"]`);
  if (!container) return;
  const btn = container.querySelector(".settings-test");
  const status = container.querySelector(".settings-status");

  let channel;
  if (btn.dataset.channelSummarizer) {
    channel = container.querySelector("[data-key='summarizer_backend']").value;
    if (channel === "none") {
      if (status) { status.textContent = "Selecciona un backend primero"; status.className = "settings-status hint err"; }
      return;
    }
  } else {
    channel = btn.dataset.channel;
  }

  const origText = btn.textContent;
  btn.disabled = true;
  btn.textContent = "Probando…";
  if (status) { status.textContent = ""; status.className = "settings-status hint"; }

  try {
    const res = await fetch(`${API}/settings/test`, {
      method: "POST",
      headers: authHeaders(),
      body: JSON.stringify({ channel }),
    });
    const data = await res.json();
    if (status) {
      status.textContent = data.message;
      status.className = "settings-status hint " + (data.ok ? "ok" : "err");
    }
  } catch (e) {
    if (status) { status.textContent = "Error de red: " + e; status.className = "settings-status hint err"; }
  } finally {
    btn.disabled = false;
    btn.textContent = origText;
  }
}

// Eventos — Guardar
document.querySelectorAll(".settings-save").forEach((btn) => {
  btn.addEventListener("click", () => {
    const group = btn.closest(".settings-group").dataset.group;
    saveSettings(group);
  });
});

// Eventos — Probar conexión
document.querySelectorAll(".settings-test").forEach((btn) => {
  btn.addEventListener("click", () => {
    const group = btn.closest(".settings-group").dataset.group;
    testSettings(group);
  });
});

// Cargar ajustes al abrir la pestaña
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    if (btn.dataset.tab === "settings") loadSettings();
  });
});