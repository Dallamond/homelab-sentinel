"""
Modo `agent`: se ejecuta con `python -m app.agent` en cada host adicional
(ej. el NAS). No monta base de datos ni dashboard: descubre servicios,
pregunta al servidor central qué fuentes están activas, y hace streaming
de solo esas hacia POST /api/ingest en lotes pequeños.

Uso típico (docker-compose en el NAS):
    ROLE=agent HOST_NAME=nas SERVER_URL=http://minipc:8088 AGENT_API_KEY=... \
    python -m app.agent
"""
from __future__ import annotations

import asyncio
import logging

import httpx

from app.collectors.discovery import discover_sources
from app.collectors.docker_collector import DockerCollector
from app.collectors.journald_collector import JournaldCollector
from app.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

_headers = {"X-Agent-Key": settings.agent_api_key}
_enabled_cache: set[tuple[str, str]] = set()


async def _register_and_refresh_enabled() -> None:
    async with httpx.AsyncClient(base_url=settings.server_url, headers=_headers, timeout=15) as client:
        while True:
            try:
                found = await discover_sources()
                payload = [
                    {"host": settings.host_name, "source_type": t.value, "source_name": n}
                    for t, n in found
                ]
                if payload:
                    await client.post("/api/sources/register", json=payload)

                resp = await client.get("/api/sources", params={"host": settings.host_name})
                resp.raise_for_status()
                global _enabled_cache
                _enabled_cache = {
                    (s["source_type"], s["source_name"]) for s in resp.json() if s["enabled"]
                }
                logger.info("Fuentes activas en %s: %d", settings.host_name, len(_enabled_cache))
            except Exception:  # noqa: BLE001
                logger.exception("Fallo registrando/actualizando fuentes contra el servidor")
            await asyncio.sleep(settings.agent_discovery_interval_seconds)


async def _push_loop(queue: asyncio.Queue) -> None:
    async with httpx.AsyncClient(base_url=settings.server_url, headers=_headers, timeout=15) as client:
        buffer: list[dict] = []
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=settings.agent_push_interval_seconds)
                buffer.append(event)
            except asyncio.TimeoutError:
                pass

            if buffer and (len(buffer) >= 50 or queue.empty()):
                try:
                    await client.post(
                        "/api/ingest",
                        json={"host": settings.host_name, "events": buffer},
                    )
                    buffer = []
                except Exception:  # noqa: BLE001
                    logger.exception("Fallo enviando lote de eventos al servidor, se reintenta en el próximo ciclo")


async def _collect_into_queue(collector, queue: asyncio.Queue) -> None:
    async for event in collector.stream():
        if (event["source_type"].value, event["source_name"]) not in _enabled_cache:
            continue
        serializable = {**event, "source_type": event["source_type"].value, "severity": event["severity"].value}
        await queue.put(serializable)


async def main() -> None:
    queue: asyncio.Queue = asyncio.Queue()
    tasks = [
        asyncio.create_task(_register_and_refresh_enabled()),
        asyncio.create_task(_push_loop(queue)),
    ]
    if settings.collect_journald:
        tasks.append(asyncio.create_task(_collect_into_queue(JournaldCollector(), queue)))
    if settings.collect_docker:
        tasks.append(asyncio.create_task(_collect_into_queue(DockerCollector(), queue)))

    logger.info("Agente arrancado: host=%s -> server=%s", settings.host_name, settings.server_url)
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
