"""
Collector de logs de contenedores Docker en tiempo real.

Usa la Docker SDK (`docker.from_env()`) para descubrir contenedores en
marcha y engancharse al stream de logs de cada uno de forma concurrente.
Detecta contenedores nuevos periódicamente para no perderse servicios que
arrancan después que el collector.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import re
from typing import AsyncIterator

import docker
from docker.models.containers import Container

from app.collectors.base import RawEvent
from app.config import settings
from app.db.models import Severity, SourceType

logger = logging.getLogger(__name__)

_LEVEL_PATTERNS = [
    (re.compile(r"\b(CRITICAL|FATAL)\b", re.IGNORECASE), Severity.critical),
    (re.compile(r"\b(ERROR|ERR|EXCEPTION|TRACEBACK)\b", re.IGNORECASE), Severity.error),
    (re.compile(r"\b(WARN|WARNING)\b", re.IGNORECASE), Severity.warning),
    (re.compile(r"\b(DEBUG)\b", re.IGNORECASE), Severity.debug),
]


def _guess_severity(message: str) -> Severity:
    for pattern, severity in _LEVEL_PATTERNS:
        if pattern.search(message):
            return severity
    return Severity.info


class DockerCollector:
    name = "docker"

    def __init__(self, container_filters: list[str] | None = None, rescan_interval: int = 30) -> None:
        self.container_filters = container_filters or settings.docker_containers
        self.rescan_interval = rescan_interval
        try:
            self._client = docker.DockerClient(base_url=settings.docker_socket)
        except Exception:  # noqa: BLE001
            logger.exception("No se pudo conectar al daemon Docker en %s", settings.docker_socket)
            self._client = None
        self._watched: set[str] = set()
        self._queue: asyncio.Queue[RawEvent] = asyncio.Queue()

    def _matches_filter(self, container: Container) -> bool:
        if not self.container_filters:
            return True
        return any(container.name.startswith(prefix) for prefix in self.container_filters)

    async def _watch_container(self, container: Container) -> None:
        logger.info("Enganchando a logs de contenedor: %s", container.name)
        loop = asyncio.get_event_loop()

        def _blocking_log_reader() -> None:
            try:
                for line in container.logs(stream=True, follow=True, since=dt.datetime.now(dt.timezone.utc)):
                    message = line.decode("utf-8", errors="replace").rstrip()
                    if not message:
                        continue
                    event = RawEvent(
                        timestamp=dt.datetime.now(dt.timezone.utc),
                        source_type=SourceType.docker,
                        source_name=container.name,
                        severity=_guess_severity(message),
                        message=message,
                        raw=message,
                    )
                    asyncio.run_coroutine_threadsafe(self._queue.put(event), loop)
            except Exception:  # noqa: BLE001 - un contenedor caído no debe tumbar el collector
                logger.exception("Se perdió el stream de logs de %s", container.name)

        await loop.run_in_executor(None, _blocking_log_reader)

    async def _discovery_loop(self) -> None:
        while True:
            if self._client is None:
                await asyncio.sleep(self.rescan_interval)
                continue
            try:
                for container in self._client.containers.list():
                    if container.name in self._watched:
                        continue
                    if not self._matches_filter(container):
                        continue
                    self._watched.add(container.name)
                    asyncio.create_task(self._watch_container(container))
            except Exception:  # noqa: BLE001
                logger.exception("Fallo listando contenedores Docker")
            await asyncio.sleep(self.rescan_interval)

    async def stream(self) -> AsyncIterator[RawEvent]:
        asyncio.create_task(self._discovery_loop())
        while True:
            yield await self._queue.get()
