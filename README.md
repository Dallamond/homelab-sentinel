# 🛡️ homelab-sentinel

> Real-time log monitoring, rule-based alerting and AI-generated summaries for a self-hosted homelab (Proxmox / NAS / Docker).
> Built as a portfolio project — see below for the Spanish version.

Lightweight, self-hosted alternative to bolting a full ELK/Loki stack onto a
homelab just to know when something breaks. It tails `journald` and Docker
container logs across one or several hosts, evaluates them against
configurable rules, notifies you (dashboard, Telegram, email), and uses an
LLM (Gemini Flash, Ollama, or any OpenAI-compatible API) to turn raw logs
into weekly/monthly human-readable summaries — plus an on-demand "explain
this log line to me" button.

---

## Features

- **Real-time collectors** for `journald` (systemd units) and Docker container logs, with automatic service discovery — no need to hardcode what to watch.
- **Opt-in monitoring**: every discovered service/container starts disabled; you pick what to actually ingest from the dashboard.
- **Configurable rule engine** (`rules.yaml`): regex pattern + minimum severity + threshold within a sliding time window + cooldown, fully declarative, no code changes needed to add a rule.
- **Pluggable notifiers**: dashboard (always), Telegram, email (SMTP/Gmail) — enable per rule.
- **Pluggable AI summarizer**: swap between Gemini Flash (free tier), a local Ollama model, or any OpenAI-compatible endpoint via one environment variable.
- **Weekly/monthly smart reports**: aggregated stats (error spikes, noisiest services, alert history) turned into a markdown summary with concrete recommendations by the LLM.
- **"Explain this to me"**: click any log line in the dashboard and get a plain-language explanation of what it means and whether you should worry.
- **Multi-host**: run in `standalone` mode on a single machine, or split into a central `server` (dashboard + DB + rules + summaries) and lightweight `agent`s on every other host (e.g. a NAS) that just discover, filter and forward.
- **Self-contained dashboard**: no Grafana dependency, single dark-themed page, live-refreshing feed and charts.

## Architecture

```
┌─────────────────────────┐        ┌─────────────────────────┐
│   Host A (agent)        │        │   Host B (server, e.g.  │
│   e.g. NAS               │  HTTP  │   mini PC)               │
│  journald + docker logs │ ─────▶ │  FastAPI + SQLite/PG     │
│  discovery + filtering  │        │  rule engine + dispatch  │
└─────────────────────────┘        │  scheduler (weekly/      │
                                    │  monthly LLM summaries)  │
                                    │  dashboard (static SPA)  │
                                    └─────────────────────────┘
```

In `standalone` mode (default, single host) the agent and server logic run
in the same process — simplest possible setup.

## Quick start (single host, e.g. your mini PC)

```bash
git clone <your-fork-url> homelab-sentinel
cd homelab-sentinel
cp .env.example .env
cp rules.example.yaml rules.yaml
# edit .env: at minimum set AGENT_API_KEY, and GEMINI_API_KEY if you want summaries

docker compose up -d --build
```

Open `http://<host-ip>:8088`, go to the **Fuentes** tab, and enable the
services/containers you want to monitor. That's it — events start flowing
and rules start evaluating immediately.

## Adding a second host (e.g. your NAS)

On the server host, note the `AGENT_API_KEY` from `.env`. On the NAS:

```bash
git clone <your-fork-url> homelab-sentinel
cd homelab-sentinel
SERVER_URL=http://<server-ip>:8088 AGENT_API_KEY=<same-key> HOST_NAME=nas \
  docker compose -f docker-compose.agent.yml up -d --build
```

The NAS will register its discovered services against the central
dashboard; enable them the same way as any other host.

## Configuration

All configuration lives in `.env` (see `.env.example`) and `rules.yaml` (see
`rules.example.yaml` for 5 ready-made rules: OOM killer, repeated service
failures, SSH brute-force attempts, crash-looping containers, disk full).

## Running tests

```bash
pip install -r requirements-dev.txt
pytest
ruff check app tests
```

CI (`.github/workflows/ci.yml`) runs both on every push/PR.

## Tech stack

Python 3.12, FastAPI, SQLAlchemy 2.0 (async), SQLite (Postgres-ready),
APScheduler, Docker SDK, vanilla JS + Chart.js for the dashboard.

## License

MIT — see [LICENSE](LICENSE).

---

## 🇪🇸 Versión en español

Herramienta de monitorización de logs en tiempo real para un homelab
autogestionado (Proxmox / NAS / Docker), con alertas basadas en reglas
configurables y resúmenes generados por IA.

### Por qué existe

En vez de montar un stack ELK/Loki completo solo para enterarte de que algo
se ha roto, `homelab-sentinel` lee logs de `journald` y de contenedores
Docker en uno o varios hosts, los evalúa contra reglas que tú defines, te
avisa (dashboard, Telegram, email) y usa un LLM (Gemini Flash gratuito,
Ollama local, o cualquier API compatible con OpenAI) para convertir logs en
bruto en resúmenes semanales/mensuales legibles — además de un botón de
"explícame esto" para cualquier línea de log que te resulte rara.

### Características

- Descubrimiento automático de servicios systemd y contenedores Docker — no hay que escribir a mano qué vigilar.
- Todo empieza desactivado: tú decides desde el dashboard qué fuentes activar.
- Motor de reglas declarativo (`rules.yaml`): patrón + severidad mínima + umbral en ventana de tiempo + cooldown, sin tocar código.
- Notificadores plugables: dashboard (siempre), Telegram, email — configurables por regla.
- Backend de resúmenes intercambiable: Gemini Flash, Ollama local, o cualquier API OpenAI-compatible, con una sola variable de entorno.
- Resúmenes semanales/mensuales con estadísticas y recomendaciones concretas.
- Multi-host: modo `standalone` en una sola máquina, o servidor central + agentes ligeros en cada host adicional (ej. tu NAS).
- Dashboard propio, sin depender de Grafana, sin login (pensado para red local).

### Arranque rápido

Ver la sección en inglés arriba — los comandos son idénticos.

### Autor

Lucas Fernández Carrasco — proyecto de portfolio, construido sobre un
homelab real (Proxmox + NAS + Raspberry Pi).
