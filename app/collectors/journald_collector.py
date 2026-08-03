"""
Collector de logs del sistema vía journald (systemd-journal).

Usa `journalctl -f -o json` en un subproceso y parsea línea a línea en
streaming, en vez de acoplarse a la librería nativa systemd-python (que no
siempre está disponible fuera de Linux con systemd, p. ej. en el propio
entorno de desarrollo). Esto hace el collector portable y fácil de probar.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
from typing import AsyncIterator

from app.collectors.base import RawEvent
from app.config import settings
from app.db.models import Severity, SourceType

logger = logging.getLogger(__name__)

# Mapeo de prioridad syslog (RFC 5424) -> severidad interna
_PRIORITY_MAP = {
    "0": Severity.critical,  # emerg
    "1": Severity.critical,  # alert
    "2": Severity.critical,  # crit
    "3": Severity.error,     # err
    "4": Severity.warning,   # warning
    "5": Severity.info,      # notice
    "6": Severity.info,      # info
    "7": Severity.debug,     # debug
}


class JournaldCollector:
    name = "journald"

    def __init__(self, units: list[str] | None = None) -> None:
        self.units = units or settings.journald_units

    def _build_command(self) -> list[str]:
        cmd = ["journalctl", "-f", "-o", "json", "--no-pager"]
        for unit in self.units:
            cmd += ["-u", unit]
        return cmd

    async def stream(self) -> AsyncIterator[RawEvent]:
        cmd = self._build_command()
        logger.info("Arrancando journald collector: %s", " ".join(cmd))
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        assert proc.stdout is not None
        try:
            async for line in proc.stdout:
                event = self._parse_line(line)
                if event is not None:
                    yield event
        finally:
            if proc.returncode is None:
                proc.terminate()

    def _parse_line(self, raw_line: bytes) -> RawEvent | None:
        try:
            data = json.loads(raw_line.decode("utf-8", errors="replace"))
        except json.JSONDecodeError:
            return None

        message = data.get("MESSAGE", "")
        if isinstance(message, list):
            # journald puede mandar el mensaje como array de bytes
            message = bytes(message).decode("utf-8", errors="replace")

        unit = data.get("_SYSTEMD_UNIT") or data.get("SYSLOG_IDENTIFIER") or "unknown"
        priority = str(data.get("PRIORITY", "6"))
        usec = data.get("__REALTIME_TIMESTAMP")
        timestamp = (
            dt.datetime.fromtimestamp(int(usec) / 1_000_000, tz=dt.timezone.utc)
            if usec
            else dt.datetime.now(dt.timezone.utc)
        )

        return RawEvent(
            timestamp=timestamp,
            source_type=SourceType.journald,
            source_name=unit,
            severity=_PRIORITY_MAP.get(priority, Severity.info),
            message=message,
            raw=raw_line.decode("utf-8", errors="replace").strip(),
        )
