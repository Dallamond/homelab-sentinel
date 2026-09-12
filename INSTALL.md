# 📦 Guía de instalación — homelab-sentinel

> Guía paso a paso para desplegar homelab-sentinel en tu primer nodo (el mini PC Chuwi con Debian 12). Dos caminos: **Docker** (recomendado) y **Python directo** (clase systemd).

---

## 0. Plan

| Nodo | Rol | Cómo se despliega |
|---|---|---|
| Mini PC Chuwi (`192.168.1.100`, Debian 12) | **Servidor + dashboard** (`standalone`) | `docker compose up -d` |
| NAS u otros hosts (más adelante) | **Agente** (envía logs al servidor) | `docker compose -f docker-compose.agent.yml up -d` |

En este primer despliegue solo toca el mini PC en modo `standalone`: un solo
contenedor hace de agente + servidor + dashboard y vigila los servicios y
contenedores **del propio mini PC** (Immich, OMV, etc.).

---

## 1. Requisitos previos (en el mini PC)

```bash
sudo apt update && sudo apt install -y git docker-ce docker-compose-plugin
```

Verifica Docker:

```bash
docker --version && docker compose version
```

Confirma que tu usuario tiene acceso al socket de Docker (si no estás en el
grupo `docker`, añade a tu usuario y vuelve a iniciar sesión):

```bash
sudo usermod -aG docker $USER
newgrp docker
docker ps   # → debe listar contenedores, no dar error de permisos
```

> homelab-sentinel lee los logs de otros contenedores montando el socket de
> Docker en modo **solo lectura** (`:ro`). Es seguro: no puede controlar
> contenedores, solo leer sus logs.

---

## 2. Descarga el código

En el mini PC:

```bash
sudo mkdir -p /opt && cd /opt
sudo git clone https://github.com/Dallamond/homelab-sentinel.git
sudo chown -R $USER:$USER /opt/homelab-sentinel
cd /opt/homelab-sentinel
```

---

## 3. Configuración

Copia las plantillas y edítalas:

```bash
cp .env.example .env
cp rules.example.yaml rules.yaml
nano .env
```

### Mínimo imprescindible en `.env`

```ini
ROLE=standalone
HOST_NAME=chuwi          # nombre de este nodo, como lo verás en el dashboard
AGENT_API_KEY=<clave-larga-y-aleatoria>
```

Genera la clave con `openssl rand -hex 24` y pégala. `AGENT_API_KEY` es la
clave que usarán en el futuro los agentes remotos (NAS) para autenticarse;
aunque ahora solo haya un nodo, ponla desde el principio.

### Opcionales según lo que quieras

**1. Proteger el dashboard** (recomendado si la web será accesible desde LAN):

```ini
DASHBOARD_API_KEY=<otra-clave-larga-distinta>
```

Si la dejas vacía, el dashboard estará abierto (apto solo para LAN de
confianza). Si la pones, al abrir el dashboard te pedirá la clave la primera
vez y la guardará en el navegador.

**2. Resúmenes con IA — Gemini Flash (gratis 🔑):**

Saca una API key en https://aistudio.google.com/apikey (gratis, con cuota) y:

```ini
SUMMARIZER_BACKEND=gemini
GEMINI_API_KEY=<tu-clave>
```

**3. Alertas a Telegram:**

Habla con @BotFather, crea un bot y obtén el chat_id; luego:

```ini
TELEGRAM_ENABLED=true
TELEGRAM_BOT_TOKEN=<token-del-bot>
TELEGRAM_CHAT_ID=<tu-chat-id>
```

**4. Alertas por email (Gmail):**

En Gmail crea una "contraseña de aplicación" de 16 caracteres y:

```ini
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu_correo@gmail.com
SMTP_PASSWORD=<app-password-16-caracteres>
EMAIL_FROM=tu_correo@gmail.com
EMAIL_TO=tu_correo@gmail.com
```

> Las 4 cosas son opcionales e independientes. Con solo `ROLE`/`HOST_NAME`/
> `AGENT_API_KEY` ya tienes un dashboard funcional que vigila, muestra
> eventos y alerta **por dashboard**.

### `rules.yaml`

Viene con 5 reglas listas (OOM killer, fallos repetidos de servicio, fuerza
bruta SSH, contenedores en bucle de reinicio, disco lleno). No hace falta
tocarlas para empezar. Se pueden recargar en caliente desde el dashboard
(pestaña **Reglas** → *Recargar rules.yaml*), sin reiniciar el contenedor.

---

## 4. Arrancar con Docker

```bash
cd /opt/homelab-sentinel
docker compose up -d --build
```

Primera vez compila la imagen (un par de minutos). Luego queda corriendo con
`restart: unless-stopped` (se levanta solo al reiniciar el mini PC).

Comprueba que está vivo:

```bash
docker compose ps
```

Espera 3–5 segundos y verifica la API:

```bash
curl -s http://localhost:8088/api/health
```

Debe responder algo como:

```json
{"status":"ok","role":"standalone","host":"chuwi","auth_required":false}
```

---

## 5. Abrir el dashboard

Desde cualquier ordenador de tu LAN:

```
http://192.168.1.100:8088
```

Pasos para el primer uso:

1. La tarjeta del host **chuwi** aparecerá en la parte superior.
2. Ve a la pestaña **Fuentes**: verás los servicios systemd y contenedores
   Docker descubiertos automáticamente en el mini PC.
3. Activa las fuentes que quieras vigilar (ej. `immich.service`, `docker`).
   La monitorización es **opt-in**: nada se vigila hasta que lo actives.
4. En **Feed en vivo** empiezan a fluir los eventos. Si hay un error, puedes
   pulsar **"Explícame esto"** en cualquier línea.

> Para que los eventos fluyan rápido al probar, activa fuentes como
> `systemd-journald` (todo el journal) o un servicio concreto, y genera
> algo de tráfico (un reinicio de servicio, un contenedor que suba).

---

## 6. Añadir otro host más adelante (ej. el NAS)

En el servidor (mini PC) ya está `AGENT_API_KEY`. Ahora, en el NAS:

```bash
cd /opt
sudo git clone https://github.com/Dallamond/homelab-sentinel.git
cd homelab-sentinel
SERVER_URL=http://192.168.1.100:8088 AGENT_API_KEY=<misma-key> HOST_NAME=nas \
  docker compose -f docker-compose.agent.yml up -d --build
```

El NAS envía a `192.168.1.100:8088` sus logs; el dashboard central muestra
ambos hosts y desde ahí activas sus fuentes. **Solo hay que instalar y abrir
el dashboard en el mini PC** — los hosts adicionales son agentes mudos sin
interfaz.

---

## 7. Actualizar el despliegue

```bash
cd /opt/homelab-sentinel
git pull
docker compose up -d --build
```

La base de datos vive en `./data/` (volumen montado en el contenedor), así
que **no se pierde nada** al actualizar. Las reglas (`rules.yaml`) también
son tuyas y persisten.

---

## 8. Camino alternativo: Python directo (sin Docker)

Para quien prefiera no usar Docker. En el mini PC:

```bash
sudo apt install -y python3.12 python3.12-venv
cd /opt/homelab-sentinel
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env    # igual que en el apartado 3
cp rules.example.yaml rules.yaml
```

Arranque manual:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8088
```

Para que quede como servicio, copia la unidad de ejemplo:

```bash
sudo cp deploy/homelab-sentinel.service.example \
        /etc/systemd/system/homelab-sentinel.service
sudo nano /etc/systemd/system/homelab-sentinel.service   # ajusta rutas/User
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-sentinel
```

> La instalación Docker solo necesita `systemd` + `ca-certificates`
> (instalados ya en la imagen). En el modo Python directo, además, el
> contenedor no está implicado: el proceso usa el journal y el socket Docker
> del host directamente.

---

## 9. Resolución de problemas

| Síntoma | Causa probable | Solución |
|---|---|---|
| `docker compose up` da error de permisos | Usuario sin grupo `docker` | `sudo usermod -aG docker $USER` + relogin |
| El contenedor se reinicia en bucle | `.env` mal formado (claves rotas) | `docker compose logs` y corrige `.env` |
| No aparecen fuentes en el dashboard | El agente no ha hecho el descubrimiento aún | Espera ~1 minuto y recarga la pestaña Fuentes |
| El dashboard da **401 / pide clave** | `DASHBOARD_API_KEY` configurada | Introduce la clave, se guarda en el navegador |
| `curl /api/health` no responde | El contenedor aún compilando o caído | `docker compose ps` y `docker compose logs -f` |
| No llegan eventos pese a fuente activa | La fuente activada no genera logs | Activa `systemd-journald` (todo el journal) para ver inmediatamente |

### Comandos útiles

```bash
docker compose logs -f            # logs del contenedor en tiempo real
docker compose down && docker compose up -d --build   # recrear desde cero
docker compose exec sentinel cat /app/data/sentinel.db   # sanity check db
```

---

## Guía rápida (recorta y pega)

```bash
# En el mini PC, tras tener docker instalado:
cd /opt
sudo git clone https://github.com/Dallamond/homelab-sentinel.git
sudo chown -R $USER:$USER /opt/homelab-sentinel
cd /opt/homelab-sentinel
cp .env.example .env && cp rules.example.yaml rules.yaml
nano .env
docker compose up -d --build
# → abre http://192.168.1.100:8088
```