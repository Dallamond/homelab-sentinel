"""
Interfaz común que deben implementar todos los collectors.
Un collector es un generador async infinito de LogEvent "en bruto"
(dict, todavía sin persistir) que el pipeline principal consume.
"""
from __future__ import annotations

import datetime as dt
from typing import AsyncIterator, Protocol, TypedDict

from app.db.models import Severity, SourceType


class RawEvent(TypedDict):
    timestamp: dt.datetime
    source_type: SourceType
    source_name: str
    severity: Severity
    message: str
    raw: str


class Collector(Protocol):
    name: str

    async def stream(self) -> AsyncIterator[RawEvent]:
        """Debe hacer yield de eventos indefinidamente (o hasta que se cancele la tarea)."""
        ...
