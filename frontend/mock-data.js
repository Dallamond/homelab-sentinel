/*
 * Modo demo: intercepta window.fetch para /api/* y devuelve datos falsos,
 * sin necesidad de arrancar el backend real. Se carga SOLO en demo.html,
 * antes de app.js, así que el resto del dashboard funciona sin tocar nada.
 * Los toggles de "Fuentes" y los botones de generar resumen / explicar
 * funcionan de mentira (delay simulado) para que puedas ver la interacción
 * completa.
 */

const SEVS = ["debug", "info", "warning", "error", "critical"];
const HOSTS = ["minipc-demo", "nas-demo"];
const SVC = [
  ["journald", "immich.service"],
  ["journald", "sshd.service"],
  ["journald", "syncthing.service"],
  ["docker", "proxmox-exporter"],
  ["docker", "omv-web"],
];
const MSGS = {
  debug: "Health check tick",
  info: "Started scheduled backup job",
  warning: "Response time above 500ms",
  error: "Connection refused by upstream service",
  critical: "Out of memory: Killed process 1234 (immich-server)",
};

function randomEvents(n) {
  const now = Date.now();
  return Array.from({ length: n }, (_, i) => {
    const sev = SEVS[Math.floor(Math.random() * SEVS.length)];
    const [type, name] = SVC[Math.floor(Math.random() * SVC.length)];
    return {
      id: i + 1,
      timestamp: new Date(now - Math.random() * 3600_000).toISOString(),
      host: HOSTS[Math.floor(Math.random() * HOSTS.length)],
      source_type: type,
      source_name: name,
      severity: sev,
      message: MSGS[sev],
    };
  }).sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
}

let MOCK_EVENTS = randomEvents(60);
let nextEventId = MOCK_EVENTS.length + 1;

// Simula que los hosts siguen mandando logs de verdad: cada vez que la
// dashboard pide /api/events, hay probabilidad de que "lleguen" eventos
// nuevos con timestamp = ahora mismo. minipc-demo manda casi siempre;
// nas-demo a veces se queda callado un rato, para que puedas ver cómo el
// panel de hosts pasa de verde a amarillo/gris con el tiempo.
function injectFreshEvents() {
  const now = new Date().toISOString();
  const additions = [];

  if (Math.random() < 0.85) {
    const [type, name] = SVC[Math.floor(Math.random() * SVC.length)];
    const sev = SEVS[Math.floor(Math.random() * SEVS.length)];
    additions.push({
      id: nextEventId++,
      timestamp: now,
      host: "minipc-demo",
      source_type: type,
      source_name: name,
      severity: sev,
      message: MSGS[sev],
    });
  }
  if (Math.random() < 0.3) {
    const [type, name] = SVC[Math.floor(Math.random() * SVC.length)];
    const sev = SEVS[Math.floor(Math.random() * SEVS.length)];
    additions.push({
      id: nextEventId++,
      timestamp: now,
      host: "nas-demo",
      source_type: type,
      source_name: name,
      severity: sev,
      message: MSGS[sev],
    });
  }

  if (additions.length) {
    MOCK_EVENTS = [...additions, ...MOCK_EVENTS].slice(0, 150);
  }
}

const MOCK_ALERTS = [
  {
    id: 1,
    created_at: new Date(Date.now() - 600_000).toISOString(),
    rule_name: "OOM killer",
    severity: "critical",
    host: "minipc-demo",
    source_name: "immich.service",
    summary: "Regla 'OOM killer' disparada por immich.service (minipc-demo): Out of memory: Killed process 1234",
    notified_telegram: true,
    notified_email: false,
  },
  {
    id: 2,
    created_at: new Date(Date.now() - 3_600_000).toISOString(),
    rule_name: "Intentos de login fallidos (SSH)",
    severity: "warning",
    host: "nas-demo",
    source_name: "sshd.service",
    summary: "Regla 'Intentos de login fallidos (SSH)' disparada por sshd.service (nas-demo): Failed password for invalid user admin",
    notified_telegram: true,
    notified_email: true,
  },
  {
    id: 3,
    created_at: new Date(Date.now() - 7_200_000).toISOString(),
    rule_name: "Contenedor reiniciando en bucle",
    severity: "error",
    host: "nas-demo",
    source_name: "omv-web",
    summary: "Regla 'Contenedor reiniciando en bucle' disparada por omv-web (nas-demo): exited with code 137, Restarting",
    notified_telegram: false,
    notified_email: false,
  },
];

let MOCK_SOURCES = HOSTS.flatMap((host) =>
  SVC.map(([type, name], i) => ({
    id: `${host}-${i}`,
    host,
    source_type: type,
    source_name: name,
    enabled: Math.random() > 0.4,
    last_seen: new Date(Date.now() - Math.random() * 600_000).toISOString(),
  }))
);

const MOCK_SUMMARY = {
  id: 1,
  created_at: new Date().toISOString(),
  period: "weekly",
  period_start: new Date(Date.now() - 7 * 86400_000).toISOString(),
  period_end: new Date().toISOString(),
  backend_used: "gemini (demo)",
  content_md:
    "## Resumen general\nSemana tranquila en general, con un pico puntual de memoria en Immich el martes.\n\n" +
    "## Puntos destacados\n- 3 alertas en total, ninguna crítica sostenida.\n- omv-web reinició 3 veces seguidas el jueves.\n\n" +
    "## Alertas críticas\n1 evento OOM en immich.service, resuelto tras reinicio automático.\n\n" +
    "## Recomendaciones\n- Revisa el límite de memoria asignado a Immich.\n- Investiga por qué omv-web reinicia en bucle los jueves.\n- Considera rotar logs de sshd, hay bastante ruido de intentos de login.",
};

// Reglas "reales": mismas shape que /api/rules y mismas reglas de rules.yaml
let MOCK_RULES = [
  {
    name: "OOM killer",
    match: "Out of memory|oom-kill|oom_kill",
    min_severity: "warning",
    source_type: "any",
    threshold: 1,
    window_seconds: 60,
    cooldown_seconds: 900,
    severity: "critical",
    notify: ["telegram", "email"],
  },
  {
    name: "Fallo repetido de servicio",
    match: "\\bfailed\\b|\\berror\\b",
    min_severity: "error",
    source_type: "any",
    threshold: 5,
    window_seconds: 300,
    cooldown_seconds: 1800,
    severity: "error",
    notify: ["telegram"],
  },
  {
    name: "Intentos de login fallidos (SSH)",
    match: "Failed password|authentication failure",
    min_severity: "warning",
    source_type: "journald",
    threshold: 3,
    window_seconds: 300,
    cooldown_seconds: 900,
    severity: "warning",
    notify: ["telegram", "email"],
  },
  {
    name: "Contenedor reiniciando en bucle",
    match: "Restarting|exited with code",
    min_severity: "warning",
    source_type: "docker",
    threshold: 3,
    window_seconds: 600,
    cooldown_seconds: 1800,
    severity: "error",
    notify: ["telegram"],
  },
  {
    name: "Disco casi lleno",
    match: "No space left on device",
    min_severity: "error",
    source_type: "any",
    threshold: 1,
    window_seconds: 60,
    cooldown_seconds: 3600,
    severity: "critical",
    notify: ["telegram", "email"],
  },
];

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function jsonResponse(data) {
  return new Response(JSON.stringify(data), { status: 200, headers: { "Content-Type": "application/json" } });
}

const realFetch = window.fetch.bind(window);

window.fetch = async (url, options = {}) => {
  const u = typeof url === "string" ? url : url.toString();
  await delay(150 + Math.random() * 250);

  if (u.includes("/api/health")) {
    return jsonResponse({ status: "ok", role: "demo", host: "modo-demo-sin-backend" });
  }
  if (u.includes("/api/events")) {
    injectFreshEvents();
    return jsonResponse(MOCK_EVENTS);
  }
  if (u.includes("/api/alerts")) {
    return jsonResponse(MOCK_ALERTS);
  }
  if (u.match(/\/api\/sources\/[^/]+\/toggle/)) {
    const id = u.split("/").slice(-2)[0];
    MOCK_SOURCES = MOCK_SOURCES.map((s) => (String(s.id) === id ? { ...s, enabled: !s.enabled } : s));
    return jsonResponse(MOCK_SOURCES.find((s) => String(s.id) === id));
  }
  if (u.includes("/api/sources")) {
    return jsonResponse(MOCK_SOURCES);
  }
  if (u.includes("/api/summaries/generate")) {
    return jsonResponse(MOCK_SUMMARY);
  }
  if (u.includes("/api/summaries")) {
    return jsonResponse([MOCK_SUMMARY]);
  }
  if (u.includes("/api/explain")) {
    return jsonResponse({
      explanation:
        "Esto es una explicación simulada (modo demo, sin conexión a Gemini de verdad). " +
        "En la versión real, aquí el LLM te diría en 3-6 frases qué significa este log, si debes " +
        "preocuparte, y qué hacer al respecto.",
    });
  }
  if (u.includes("/api/rules/reload")) {
    // "Recarga" rules.yaml: devuelve las mismas reglas, como haría el backend
    return jsonResponse({ loaded: MOCK_RULES.length, rules: MOCK_RULES });
  }
  if (u.includes("/api/rules")) {
    return jsonResponse(MOCK_RULES);
  }

  return realFetch(url, options);
};
