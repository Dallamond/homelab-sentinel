# 🛡️ homelab-sentinel

> Monitorización de logs en tiempo real, alertas configurables y resúmenes generados por IA para un homelab autogestionado.
> Proyecto de portfolio de **Lucas Fernández Carrasco** — construido sobre un homelab real (Proxmox + NAS + Raspberry Pi).

En vez de montar un stack ELK/Loki completo solo para enterarte de que algo
se ha roto, `homelab-sentinel` lee logs de `journald` y de contenedores
Docker en uno o varios hosts, los evalúa contra reglas que tú defines, te
avisa (dashboard, Telegram, email) y usa un LLM (Gemini Flash gratuito,
Ollama local, o cualquier API compatible con OpenAI) para convertir logs en
bruto en resúmenes semanales/mensuales legibles — además de un botón de
**"explícame esto"** para cualquier línea de log que te resulte rara.

---

## ✨ Características

| Función | Descripción |
|---|---|
| **Collectors en tiempo real** | Lee `journald` (unidades systemd) y logs de contenedores Docker con descubrimiento automático de servicios |
| **Monitorización opt-in** | Todo empieza desactivado; tú decides desde el dashboard qué fuentes activar, agrupadas por host |
| **Panel de hosts en vivo** | Tarjeta por host con estado (🟢 en tiempo real / 🟡 reciente / ⚪ sin datos), última actividad y fuentes activas |
| **Motor de reglas declarativo** | `rules.yaml`: regex + severidad mínima + umbral en ventana de tiempo + cooldown — sin tocar código |
| **Notificadores plugables** | Dashboard (siempre), Telegram, email SMTP/Gmail — configurables por regla |
| **IA intercambiable** | Gemini Flash (gratis), Ollama local o cualquier API compatible con OpenAI — una sola variable de entorno |
| **Resúmenes semanales/mensuales** | Estadísticas agregadas + recomendaciones concretas del LLM |
| **"Explícame esto"** | Botón en el dashboard para explicar en lenguaje llano cualquier línea de log |
| **Multi-host** | `standalone` en una máquina o servidor central + agentes ligeros en cada host adicional |
| **Dashboard propio** | Sin depender de Grafana; buscador de texto libre, gráfico de severidad, auto-refresco |
| **Modo demo** | `frontend/demo.html` — datos simulados, sin instalar nada, doble clic para ver el diseño |

---

## 🏗️ Arquitectura

```
┌─────────────────────────┐        ┌─────────────────────────┐
│   Host A (agente)       │        │   Host B (servidor)     │
│   ej. el NAS             │  HTTP  │   ej. mini PC Chuwi     │
│  journald + docker logs │ ─────▶ │  FastAPI + SQLite/PG     │
│  descubrimiento+filtro  │        │  motor de reglas + envío │
└─────────────────────────┘        │  scheduler (resúmenes)   │
                                    │  dashboard (SPA estática)│
                                    └─────────────────────────┘
```

En modo **standalone** (por defecto) el agente y el servidor corren en el
mismo proceso: un solo contenedor hace todo. Es la configuración más simple
y la que necesitas para empezar con un solo mini PC.

---

## 🚀 Instalación

### Instalación completa (recomendada)

Sigue la guía paso a paso en **[INSTALL.md](INSTALL.md)** — incluye
despliegue en Docker, configuración de Telegram/email, resúmenes con Gemini,
añadir agentes remotos y resolución de problemas.

### Arranque rápido (un solo host)

```bash
git clone https://github.com/Dallamond/homelab-sentinel.git
cd homelab-sentinel
cp .env.example .env
cp rules.example.yaml rules.yaml
# edita .env: como mínimo AGENT_API_KEY

docker compose up -d --build
```

Abre `http://<ip-del-host>:8088`, ve a la pestaña **Fuentes** y activa los
servicios/contenedores que quieras vigilar.

---

## 📁 Configuración

Toda la configuración vive en dos archivos:

| Archivo | Qué controla |
|---|---|
| `.env` | Rol, nombre del host, claves API, notificadores, backend de IA (ver `.env.example`) |
| `rules.yaml` | Reglas de alerta: regex, severidad, umbral, cooldown (ver `rules.example.yaml` con 5 reglas listas) |

### Seguridad del dashboard

Por defecto el dashboard es abierto (apto para LAN de confianza). Si añades
`DASHBOARD_API_KEY` en `.env`, el frontend te pedirá la clave la primera
vez — la guarda en el navegador y la envía en cada petición.

### Hot-reload de reglas

Desde la pestaña **Reglas** del dashboard puedes pulsar *Recargar rules.yaml*
para recargar las reglas sin reiniciar el contenedor.

---

## 🧪 Tests y CI

```bash
pip install -r requirements-dev.txt
pytest -v
ruff check app tests
```

El workflow de CI (`.github/workflows/ci.yml`) ejecuta lint + tests en cada push/PR.

---

## 🛠️ Stack técnico

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), APScheduler |
| Base de datos | SQLite (listo para Postgres) |
| Collectors | `journalctl -f`, Docker SDK |
| IA | Gemini Flash / Ollama / OpenAI-compatible |
| Dashboard | HTML/CSS/JS vanilla + Chart.js — sin build step |
| Despliegue | Docker Compose (multi-stage) |

---

## 📄 Licencia

MIT — ver [LICENSE](LICENSE).

**Autor:** Lucas Fernández Carrasco — [lucas.impuls16@gmail.com](mailto:lucas.impuls16@gmail.com)

---

## 🇬🇧 English

Lightweight, self-hosted alternative to a full ELK/Loki stack for homelab
log monitoring. Tails `journald` and Docker logs across multiple hosts,
evaluates them against configurable rules, notifies you (dashboard, Telegram,
email), and uses an LLM (Gemini Flash, Ollama, or OpenAI-compatible) for
weekly/monthly summaries and on-demand log explanations.

**Quick start:** clone → `cp .env.example .env` → `docker compose up -d --build` → open `http://<host>:8088`.

See [INSTALL.md](INSTALL.md) for the full guide.

**Stack:** Python 3.12, FastAPI, async SQLAlchemy 2.0, SQLite, APScheduler, Docker SDK, vanilla JS + Chart.js. **License:** MIT.
