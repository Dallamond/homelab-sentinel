# 🗺️ ROADMAP — homelab-sentinel

> **Este es el documento de trabajo del proyecto.** Cada cambio que Lucas pida se anota aquí,
> se planifica, se implementa, se verifica y se despliega. La próxima sesión empieza por aquí.
>
> Última actualización: 12/09/2026 (viernes)
> Estado general: ✅ **Desplegado y operativo en el nodo**

---

## 1. Estado actual del proyecto

| Área | Estado | Notas |
|---|---|---|
| Código en GitHub | ✅ `Dallamond/homelab-sentinel` | `8211f00 feat: deployment-ready` sobre `b0d4390` (agosto) |
| Tests | ✅ **48 pasando** | pytest asyncio (ver §4) |
| Lint | ✅ Ruff limpio | `ruff check .` |
| Contenedor | ✅ `homelab-sentinel:latest` | Docker en el nodo, `restart: unless-stopped` |
| Servicio | ✅ Uvicorn en `:8088` | Dashboard + API (rol `standalone`) |
| Base de datos | SQLite (`./data/sentinel.db`) | Postgres soportado vía `requirements-postgres.txt` (no usado aún) |
| Nodo | Chuwi (`homelab-sentinel`, root) | `/opt/homelab-sentinel`, Docker Compose |

### Arquitectura en una frase
Un único contenedor `standalone` (agente + servidor + dashboard) que observa el host:
ingesta local (journald + Docker), procesa eventos, aplica reglas de alerta, resume con LLM
(opcional) y expone API + panel en `:8088`. Soporta desplegar solo el agente en otros hosts
vía `docker-compose.agent.yml`.

### Puertos / roles
- `8088` → API + dashboard (default, hora actual)
- `docker-compose.agent.yml` → modo agente remoto que envía eventos al servidor central

---

## 2. Backlog de cambios ⏳ (lo que Lucas va pidiendo)

> Cada petición se anota aquí como una entrada con formato:
> `[estado] Título — aclaración / decisiones / notas`. Estado: ⏳ pendiente · 🔧 en curso · ✅ hecho.
> Numeración por áreas para poder referenciarlas (U=urgente, A=ajustes/auth, F=frontend, D=datos/feed,
> N=alertas/notificaciones, M=multi-host/análisis, S=seguridad).
> Volcado inicial de Lucas: 12/09/2026. Todos arrancan ⏳ pendiente.

### 🔴 Urgentes — arreglar lo que está roto o hace ruido

| # | Estado | Pedido | Notas / decisiones |
|---|---|---|---|
| U1 | ⏳ | **Vendorizar Chart.js** — quitarla dependencia de CDN externo (falla sin salida a internet) | Bajarlo y servirlo desde `frontend/` (buscar dónde se importa hoy) |
| U2 | ⏳ | **Corregir modelo/versión de API de Gemini** — el 404 indica modelo inexistente en v1beta | Revisar `app/summarizer/gemini.py` y el modelo por defecto en `config.py` |
| U3 | ⏳ | **Filtrar ruido de auto-monitorización** — el propio dashboard hace polling 5s a `/api/*` y genera cientos de "200 OK" inútiles | Excluir por defecto el propio contenedor `homelab-sentinel` y sus requests `/api/*` del feed |
| U4 | ⏳ | **Agrupar tracebacks multilínea en un solo evento** — hoy sale una línea por cada `File "...", line ...` con severidad inconsistente | Plantear unirse en `local_ingest.py` / pipeline antes de persistir |

### 🔵 Ajustes + autenticación (prioridad 1 para uso normal)

| # | Estado | Pedido | Notas / decisiones |
|---|---|---|---|
| A1 | ⏳ | **Sección de Ajustes en la GUI** — formularios para SUMMARIZER_BACKEND + API key/modelo, TELEGRAM_BOT_TOKEN/CHAT_ID, credenciales SMTP, DASHBOARD_API_KEY, AGENT_API_KEY | No tocar `.env` a mano ni reconstruir |
| A2 | ⏳ | **Endpoint `POST /api/settings`** que guarde en una tabla de config en la DB y recargue en caliente | Patrón igual al botón "Recargar rules.yaml" pero para notificadores y summarizer; preferible DB a `.env` por recarga en caliente |
| A3 | ⏳ | **Secretos enmascarados** — mostrar `••••1234`, no reenviarlos en claro al frontend tras guardar | Los APIs keys/passwords nunca vuelven al cliente |
| A4 | ⏳ | **Botón "Probar conexión"** por integración (Telegram: mensaje de prueba; Gemini: llamada mínima; Email: correo de prueba) | Evita descubrir un 404 en producción a las bravas |
| A5 | ⏳ | **Activar/mostrar `DASHBOARD_API_KEY`** — sobre todo ahora que Ajustes guardará secretos | Importante si se expone fuera de la LAN |

### 🎨 Frontend / UX

| # | Estado | Pedido | Notas / decisiones |
|---|---|---|---|
| F1 | ⏳ | **GUI reordenable/redimensionable** — grid tipo Gridstack.js o React Grid Layout; arrastrar y redimensionar bloques (feed, gráfico, filtro, fuentes) | Frontend medio-grande; no toca backend. Guardar layout en localStorage por usuario (o DB si persiste entre dispositivos) |
| F2 | ⏳ | **Editor de rules.yaml integrado** en la pestaña "Reglas" (no solo el botón de recarga) | Evita entrar por SSH a tocar una regla |
| F3 | ⏳ | **Indicador visual en el feed** cuando una línea disparó una alerta | Ahora "Alertas" está separado y cuesta correlacionar |
| F4 | ⏳ | **WebSocket en vez de polling HTTP cada 5s** para el feed en vivo | Menos carga y menos ruido en los propios logs |
| F5 | ⏳ | **Paginación real del feed** — no solo los últimos 100 | Paginación/filtrado en el backend |
| F6 | ⏳ | **Tema claro** además del oscuro actual | |
| F7 | ⏳ | **Soporte multi-idioma** de la interfaz | |
| F8 | ⏳ | **App/PWA para móvil** del dashboard | |
| F9 | ⏳ | **Widget de estado del host** — CPU, RAM, disco, temperatura | Nuevo tipo de bloque en la GUI |

### 📊 Datos / feed

| # | Estado | Pedido | Notas / decisiones |
|---|---|---|---|
| D1 | ⏳ | **Silenciar/mutear una fuente** sin desactivarla del todo | Para servicios ruidosos pero no interesantes |
| D2 | ⏳ | **Vista de logs en bruto por fuente** (no solo eventos ya procesados) | |
| D3 | ⏳ | **Backup automático (cron)** de `data/sentinel.db` | |
| D4 | ⏳ | **Exportar eventos/alertas a CSV o JSON** | |

### 🔔 Alertas / notificaciones

| # | Estado | Pedido | Notas / decisiones |
|---|---|---|---|
| N1 | ⏳ | **Alertas por disco casi lleno con tendencia** (no solo umbral fijo) | |
| N2 | ⏳ | **Reglas compuestas** — combinar varias condiciones en un solo incidente | |
| N3 | ⏳ | **Acciones rápidas desde la alerta de Telegram** (silenciar, marcar resuelto) | |
| N4 | ⏳ | **Soporte de webhook genérico** además de Telegram/Email | |
| N5 | ⏳ | **Notificación push nativa** además de Telegram/Email | |
| N6 | ⏳ | **Modo "silencio programado"** para mantenimientos | |

### 🧠 Multi-host / análisis

| # | Estado | Pedido | Notas / decisiones |
|---|---|---|---|
| M1 | ⏳ | **Timeline correlacionado entre varios hosts** (server + agentes) | |
| M2 | ⏳ | **Histórico de disponibilidad por servicio/contenedor** (uptime %) | |
| M3 | ⏳ | **Modo "resumen diferido"** — cuando no puedes reaccionar en tiempo real (ej. refugio) | |
| M4 | ⏳ | **Chat de consulta libre sobre los logs históricos** (no solo "explícame esta línea") | |
| M5 | ⏳ | **Resúmenes semanales/mensuales con comparación de tendencias**, no solo texto plano | |
| M6 | ⏳ | **Detección automática de contenedores/servicios nuevos** con alerta de "nueva fuente descubierta" | |
| M7 | ⏳ | **Healthcheck propio de Sentinel visible en el dashboard** (por si el problema es el propio Sentinel) | |

### 🔐 Seguridad / futuro

| # | Estado | Pedido | Notas / decisiones |
|---|---|---|---|
| S1 | ⏳ | **Roles de usuario/permisos** para cuando haya más de una persona usando el dashboard | Futuro |

---

> **Orden de trabajo propuesto:** empezar por U1–U4 y A1–A5 (arreglar lo roto + habilitar configuración sin rebuild).
> F2 (editor de reglas) encaja bien justo después de A1–A4 por el mismo patrón de recarga en caliente.

---

## 3. Cómo se trabaja aquí (flujo estándar)

1. **Anotar el pedido** en §2 del ROADMAP (fecha + qué + por qué).
2. **Explorar el código** relacionado antes de tocar nada (no adivinar: leer).
3. **Implementar** siguiendo la estructura existente (`app/`, `frontend/`, `tests/`).
4. **Verificar**: `pytest` (48 tests) + `ruff check .` + contexto docker.
5. **Commit + push** a `main` (mensaje claro, en español o inglés corto).
6. **Desplegar en el nodo** (ver §5) y comprobar logs.
7. **Marcar** la entrada del backlog como ✅ hecho, actualizando `Última actualización`.

> Regla del vault aplicada también aquí: **no inventar datos**. Si falta info, preguntar.

---

## 4. Comandos útiles (desde la raíz del repo)

```bash
# Tests (48)
.\.venv\Scripts\python -m pytest -q

# Lint
.\.venv\Scripts\python -m ruff check .

# Arranque local (sin docker, para desarrollo)
.\.venv\Scripts\Scripts\python -m uvicorn app.main:app --port 8088
#  (ajustar según el venv real; en Linux: source .venv/bin/activate)

# Docker local (mismo que el nodo)
docker compose up -d --build
docker compose logs --tail=30 sentinel
```

---

## 5. Despliegue al nodo (checklist real de hoy)

El nodo es **`root@homelab-sentinel`**, repo en `/opt/homelab-sentinel`.

```bash
# 0) Si ya hay cambios nuevos, primero dentro del repo local (dev):
git add -A && git commit -m "..." && git push

# En el nodo:
cd /opt/homelab-sentinel

# 1) Si git pull se queja de que un archivo local lo bloquea (p.ej. rules.yaml):
#    conservar el local y reintentar:
mv rules.yaml rules.yaml.old
git pull                          # baja la versión nueva

# 2) Reconstruir imagen (ahora el contexto cambió, ya no va a caché):
docker compose up -d --build

# 3) Comprobar que arrancó limpio (sin AttributeError):
docker compose logs --tail=30 sentinel
```

> **Errores conocidos del despliegue:**
> - `git pull aborta por untracked file` → mover el archivo a `*.old` y reintentar (nunca `rm` a ciegas).
> - `'Settings' object has no attribute 'journald_units'/'docker_containers'` → el nodo corre código antiguo; re-hacer pull + rebuild.

---

## 6. Agentes del proyecto (definidos en `.claude/agents/`)

| Agente | Rol | Cuándo usarlo |
|---|---|---|
| `roadmap` | Mantener backlog y planificación | Lucas pide un cambio → anotarlo, conectarlo con el código |
| `qa` | Verificar que nada se rompe | Tras cada cambio → pruebas, lint, sanity |
| `deploy` | Desplegar al nodo | Tras merge → pasos de §5, logs, confirmación |

> Los tres comparten el ROADMAP como fuente de verdad y anotan el `log.md` del vault en cada operación relevante.

---

## 7. Referencias rápidas

- **Estructura de la app:** `app/` → `main.py` (FastAPI), `config.py` (Settings), `pipeline.py`,
  `local_ingest.py` (journald + docker), `rules.yaml` (reglas de alerta), `scheduler.py`
  (reportes semanales `Lun 08:00` y mensuales `1º de mes 08:00`), `summarizer/` (LLM: ollama,
  gemini, openai-compat).
- **Frontend:** `frontend/` → `index.html` + `app.js` + `style.css` (panel), `demo.html`/`mock-data.js`
  (prototipo).
- **Tests:** `tests/` → 48 casos repartidos en `test_alert_engine`, `test_api`, `test_api_health`,
  `test_collectors`, `test_pipeline`.
- **Reglas de alerta:** `rules.yaml` (y `rules.example.yaml`). Se recargan en caliente vía API (`/api/rules/reload`).
- **Docs:** `README.md` (uso), `INSTALL.md` (instalación en el nodo).