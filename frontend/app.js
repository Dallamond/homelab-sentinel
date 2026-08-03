const API = "/api";

function sevClass(sev) { return `sev sev-${sev}`; }
function fmtTime(iso) { return new Date(iso).toLocaleString(); }

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
    el.textContent = `${data.status} · ${data.role} · ${data.host}`;
    el.className = "badge ok";
  } catch {
    el.textContent = "sin conexión";
    el.className = "badge down";
  }
}

// --- Events / live feed ---
let severityChart;
function renderSeverityChart(events) {
  const counts = { debug: 0, info: 0, warning: 0, error: 0, critical: 0 };
  events.forEach((e) => { counts[e.severity] = (counts[e.severity] || 0) + 1; });
  const ctx = document.getElementById("severityChart");
  const data = {
    labels: Object.keys(counts),
    datasets: [{
      data: Object.values(counts),
      backgroundColor: ["#6b7280", "#3b82f6", "#f59e0b", "#ef4444", "#dc2626"],
    }],
  };
  if (severityChart) {
    severityChart.data = data;
    severityChart.update();
  } else {
    severityChart = new Chart(ctx, { type: "doughnut", data, options: { plugins: { legend: { labels: { color: "#e6e6e6" } } } } });
  }
}

async function loadEvents() {
  const severity = document.getElementById("severityFilter").value;
  const host = document.getElementById("hostFilter").value;
  const params = new URLSearchParams({ limit: "100" });
  if (severity) params.set("severity", severity);
  if (host) params.set("host", host);

  const res = await fetch(`${API}/events?${params}`);
  const events = await res.json();

  renderSeverityChart(events);

  const tbody = document.querySelector("#eventsTable tbody");
  tbody.innerHTML = "";
  events.forEach((e) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtTime(e.timestamp)}</td>
      <td>${e.host}</td>
      <td>${e.source_name}</td>
      <td><span class="${sevClass(e.severity)}">${e.severity}</span></td>
      <td>${e.message.slice(0, 140)}</td>
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
      headers: { "Content-Type": "application/json" },
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
async function loadAlerts() {
  const res = await fetch(`${API}/alerts?limit=100`);
  const alerts = await res.json();
  const tbody = document.querySelector("#alertsTable tbody");
  tbody.innerHTML = "";
  alerts.forEach((a) => {
    const tr = document.createElement("tr");
    const notified = [a.notified_telegram ? "telegram" : null, a.notified_email ? "email" : null]
      .filter(Boolean).join(", ") || "solo dashboard";
    tr.innerHTML = `
      <td>${fmtTime(a.created_at)}</td>
      <td>${a.rule_name}</td>
      <td><span class="${sevClass(a.severity)}">${a.severity}</span></td>
      <td>${a.host} / ${a.source_name}</td>
      <td>${a.summary}</td>
      <td>${notified}</td>
    `;
    tbody.appendChild(tr);
  });
}

// --- Sources ---
async function loadSources() {
  const res = await fetch(`${API}/sources`);
  const sources = await res.json();
  const tbody = document.querySelector("#sourcesTable tbody");
  tbody.innerHTML = "";
  sources.forEach((s) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${s.host}</td>
      <td>${s.source_type}</td>
      <td>${s.source_name}</td>
      <td>${fmtTime(s.last_seen)}</td>
      <td><input type="checkbox" class="toggle" data-id="${s.id}" ${s.enabled ? "checked" : ""}/></td>
    `;
    tbody.appendChild(tr);
  });
  document.querySelectorAll(".toggle").forEach((cb) => {
    cb.addEventListener("change", async () => {
      await fetch(`${API}/sources/${cb.dataset.id}/toggle`, { method: "POST" });
    });
  });
}

// --- Summaries ---
async function loadSummaries() {
  const res = await fetch(`${API}/summaries`);
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
      <h4>Resumen ${s.period} (${s.backend_used})</h4>
      <div class="meta">${fmtTime(s.period_start)} → ${fmtTime(s.period_end)}</div>
      <div>${s.content_md.replace(/\n/g, "<br/>")}</div>
    `;
    container.appendChild(div);
  });
}

document.getElementById("genWeekly").addEventListener("click", async () => {
  await fetch(`${API}/summaries/generate?period=weekly`, { method: "POST" });
  loadSummaries();
});
document.getElementById("genMonthly").addEventListener("click", async () => {
  await fetch(`${API}/summaries/generate?period=monthly`, { method: "POST" });
  loadSummaries();
});

document.getElementById("refreshEvents").addEventListener("click", loadEvents);
document.getElementById("severityFilter").addEventListener("change", loadEvents);

// --- Init ---
checkHealth();
loadEvents();
loadAlerts();
loadSources();
loadSummaries();

setInterval(checkHealth, 15000);
setInterval(loadEvents, 5000);
setInterval(loadAlerts, 10000);
setInterval(loadSources, 20000);
