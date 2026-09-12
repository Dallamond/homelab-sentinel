"""
Genera datos de ejemplo para poder ver y tocar la dashboard sin depender
de tu homelab real: registra unas cuantas "fuentes" falsas, las activa, y
manda eventos de log simulados (algunos diseñados para disparar las reglas
de ejemplo de rules.example.yaml) contra la API local.

Uso:
    1. Arranca el servidor:  uvicorn app.main:app --reload --port 8088
    2. En otra terminal:     python scripts/seed_demo_data.py
    3. Abre http://localhost:8088 y refresca las pestañas.

No toca tu homelab real ni necesita Docker/journald instalados: solo habla
por HTTP contra el propio servidor que tienes corriendo en local.
"""
from __future__ import annotations

import datetime as dt
import random
import time

import os

import httpx

API = "http://localhost:8088/api"
AGENT_API_KEY = os.environ.get("AGENT_API_KEY", "change-me")
DASHBOARD_API_KEY = os.environ.get("DASHBOARD_API_KEY", "")
HEADERS = {"X-Agent-Key": AGENT_API_KEY}
if DASHBOARD_API_KEY:
    HEADERS["X-Dashboard-Key"] = DASHBOARD_API_KEY

FAKE_HOSTS = ["minipc-demo", "nas-demo"]

FAKE_SOURCES = [
    ("journald", "immich.service"),
    ("journald", "sshd.service"),
    ("journald", "syncthing.service"),
    ("docker", "proxmox-exporter"),
    ("docker", "omv-web"),
]

SAMPLE_MESSAGES = [
    ("info", "Started scheduled backup job"),
    ("info", "Health check OK"),
    ("warning", "Response time above 500ms"),
    ("error", "Connection refused by upstream service"),
    ("error", "Failed to write cache file"),
]

# Mensajes pensados para disparar las reglas de ejemplo (rules.example.yaml)
TRIGGER_MESSAGES = [
    ("critical", "Out of memory: Killed process 1234 (immich-server)"),
    ("warning", "Failed password for invalid user admin from 203.0.113.7"),
    ("warning", "Failed password for invalid user admin from 203.0.113.7"),
    ("warning", "Failed password for invalid user admin from 203.0.113.7"),
    ("error", "container omv-web exited with code 137, Restarting"),
    ("error", "container omv-web exited with code 137, Restarting"),
    ("error", "container omv-web exited with code 137, Restarting"),
]


def register_and_enable_sources(client: httpx.Client) -> None:
    payload = [
        {"host": host, "source_type": t, "source_name": n}
        for host in FAKE_HOSTS
        for t, n in FAKE_SOURCES
    ]
    client.post(f"{API}/sources/register", json=payload)

    sources = client.get(f"{API}/sources").json()
    for s in sources:
        if s["host"] in FAKE_HOSTS and not s["enabled"]:
            client.post(f"{API}/sources/{s['id']}/toggle")
    print(f"Fuentes de ejemplo registradas y activadas: {len(sources)}")


def push_events(client: httpx.Client, n_normal: int = 30) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    events = []

    for _ in range(n_normal):
        severity, message = random.choice(SAMPLE_MESSAGES)
        source_type, source_name = random.choice(FAKE_SOURCES)
        events.append(
            {
                "timestamp": (now - dt.timedelta(seconds=random.randint(0, 3600))).isoformat(),
                "source_type": source_type,
                "source_name": source_name,
                "severity": severity,
                "message": message,
                "raw": message,
            }
        )

    for severity, message in TRIGGER_MESSAGES:
        events.append(
            {
                "timestamp": now.isoformat(),
                "source_type": "journald",
                "source_name": "sshd.service" if "password" in message else "immich.service",
                "severity": severity,
                "message": message,
                "raw": message,
            }
        )

    for host in FAKE_HOSTS:
        resp = client.post(f"{API}/ingest", json={"host": host, "events": events})
        resp.raise_for_status()
        print(f"{host}: {resp.json()}")


def generate_summary(client: httpx.Client) -> None:
    resp = client.post(f"{API}/summaries/generate", params={"period": "weekly"})
    if resp.status_code == 200:
        print("Resumen semanal generado correctamente.")
    else:
        print(f"No se pudo generar resumen ({resp.status_code}): {resp.text}")
        print("Normal si no has configurado GEMINI_API_KEY todavía (SUMMARIZER_BACKEND=none).")


def main() -> None:
    with httpx.Client(timeout=15, headers=HEADERS) as client:
        try:
            client.get(f"{API}/health").raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(
                "No se pudo conectar a http://localhost:8088. "
                "¿Está corriendo `uvicorn app.main:app --port 8088`?"
            ) from exc

        register_and_enable_sources(client)
        time.sleep(0.5)
        push_events(client)
        generate_summary(client)

    print("\nListo. Abre http://localhost:8088 y revisa las pestañas Feed / Alertas / Fuentes / Resúmenes.")


if __name__ == "__main__":
    main()
