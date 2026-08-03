"""
Modo `standalone`: en vez de recibir eventos por HTTP (como haría el
servidor de un agente remoto), arranca los collectors localmente y los
pasa directo al pipeline en memoria. Útil cuando todo corre en un único
host y no hace falta separar agente/servidor.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging

from app.collectors.discovery import discover_sources
from app.collectors.docker_collector import DockerCollector
from app.collectors.journald_collector import JournaldCollector
from app.config import settings
from app.db.models import MonitoredSource
from app.db.session import get_session
from app.pipeline import process_event
from sqlalchemy import select

logger = logging.getLogger(__name__)


async def _sync_discovered_sources() -> None:
    while True:
        try:
            found = await discover_sources()
            now = dt.datetime.now(dt.timezone.utc)
            async with get_session() as session:
                for source_type, name in found:
                    result = await session.execute(
                        select(MonitoredSource).where(
                            MonitoredSource.host == settings.host_name,
                            MonitoredSource.source_type == source_type,
                            MonitoredSource.source_name == name,
                        )
                    )
                    existing = result.scalar_one_or_none()
                    if existing:
                        existing.last_seen = now
                    else:
                        session.add(
                            MonitoredSource(
                                host=settings.host_name,
                                source_type=source_type,
                                source_name=name,
                                enabled=False,
                                first_seen=now,
                                last_seen=now,
                            )
                        )
                await session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Fallo en el ciclo de descubrimiento de fuentes")
        await asyncio.sleep(settings.agent_discovery_interval_seconds)


async def _is_enabled(source_type: str, name: str) -> bool:
    async with get_session() as session:
        result = await session.execute(
            select(MonitoredSource).where(
                MonitoredSource.host == settings.host_name,
                MonitoredSource.source_type == source_type,
                MonitoredSource.source_name == name,
            )
        )
        source = result.scalar_one_or_none()
        return bool(source and source.enabled)


async def _run_journald() -> None:
    collector = JournaldCollector()
    async for event in collector.stream():
        if not await _is_enabled(event["source_type"].value, event["source_name"]):
            continue
        async with get_session() as session:
            await process_event(session, settings.host_name, event)


async def _run_docker() -> None:
    collector = DockerCollector()
    async for event in collector.stream():
        if not await _is_enabled(event["source_type"].value, event["source_name"]):
            continue
        async with get_session() as session:
            await process_event(session, settings.host_name, event)


async def start_local_ingest() -> None:
    """Lanza en background el descubrimiento continuo + los collectors habilitados."""
    tasks = [asyncio.create_task(_sync_discovered_sources())]
    if settings.collect_journald:
        tasks.append(asyncio.create_task(_run_journald()))
    if settings.collect_docker:
        tasks.append(asyncio.create_task(_run_docker()))
    logger.info("Ingesta local arrancada (role=%s, host=%s)", settings.role, settings.host_name)
