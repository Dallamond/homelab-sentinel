"""
Descubrimiento automático de fuentes de logs disponibles en el host:
unidades systemd activas y contenedores Docker en marcha.

El agente llama a `discover_sources()` periódicamente y registra lo
encontrado contra el servidor central (upsert). El usuario decide desde el
dashboard qué fuentes quedan `enabled=True`; el agente solo hace streaming
de las que están activas.
"""
from __future__ import annotations

import asyncio
import logging

import docker

from app.config import settings
from app.db.models import SourceType

logger = logging.getLogger(__name__)


async def discover_journald_units() -> list[str]:
    """Lista unidades systemd conocidas por journald (servicios con logs propios)."""
    proc = await asyncio.create_subprocess_exec(
        "journalctl", "-F", "_SYSTEMD_UNIT",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    units = sorted({line.strip() for line in stdout.decode("utf-8", errors="replace").splitlines() if line.strip()})
    return units


async def discover_docker_containers() -> list[str]:
    """Lista contenedores Docker existentes (en marcha o parados) en este host."""
    try:
        client = docker.DockerClient(base_url=settings.docker_socket)
        return sorted(c.name for c in client.containers.list(all=True))
    except Exception:  # noqa: BLE001 - Docker puede no estar disponible en el host
        logger.exception("No se pudo listar contenedores Docker (¿está montado el socket?)")
        return []


async def discover_sources() -> list[tuple[SourceType, str]]:
    """Devuelve la lista combinada (tipo, nombre) de todo lo detectado en este host."""
    found: list[tuple[SourceType, str]] = []
    if settings.collect_journald:
        for unit in await discover_journald_units():
            found.append((SourceType.journald, unit))
    if settings.collect_docker:
        for name in await discover_docker_containers():
            found.append((SourceType.docker, name))
    return found
