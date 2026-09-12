"""
Agrupación de líneas sueltas de un stream en eventos compuestos.

Hoy los collectors emiten una línea por evento. Un traceback de Python
(lanzado por una app dentro de un contenedor o unidad) llega entonces
fragmentado: una línea por cada `File "…", line …` y con severidades
inconsistentes según la regla que case con cada fragmento.

`TracebackMerger` bufferiza las líneas de un traceback (empezando por
`Traceback (most recent call last):`) y lo re-emite como un único evento
con el mensaje completo y la severidad máxima de sus líneas.
"""
from __future__ import annotations

from collections.abc import Iterable

from app.collectors.base import RawEvent
from app.db.models import Severity

_TRACEBACK_START = "Traceback (most recent call last):"
# Tope defensivo: un traceback desbocado no debe llenar la memoria.
_MAX_TRACEBACK_LINES = 300

_SEVERITY_ORDER = {
    Severity.debug: 0,
    Severity.info: 1,
    Severity.warning: 2,
    Severity.error: 3,
    Severity.critical: 4,
}


class TracebackMerger:
    """Bufferiza un traceback multilínea y emite un RawEvent combinado.

    Uso: pasar cada RawEvent del stream a `.feed()`; devuelve 0 o más
    eventos listos para persistir. Los eventos normales (no traceback)
    se devuelven tal cual.
    """

    def __init__(self) -> None:
        self._lines: list[RawEvent] = []

    def feed(self, event: RawEvent) -> Iterable[RawEvent]:
        message = event["message"].rstrip("\n")

        if message.startswith(_TRACEBACK_START):
            # Un traceback nuevo cierra cualquier traza pendiente anterior.
            yield from self._flush()
            self._lines = [event]
            return

        if self._lines and self._same_source(event):
            self._lines.append(event)
            # Completado cuando una línea cae a columna 0 (p. ej. la línea
            # del tipo de excepción: "ValueError: boom") o se agota el tope.
            if self._is_complete() or len(self._lines) >= _MAX_TRACEBACK_LINES:
                yield from self._flush()
            return

        # Evento normal (o cambio de fuente a mitad de traza): pasa de largo.
        yield from self._flush()
        yield event

    def flush(self) -> Iterable[RawEvent]:
        yield from self._flush()

    # --- internos ---

    def _same_source(self, event: RawEvent) -> bool:
        first = self._lines[0]
        return (
            first["source_type"] == event["source_type"]
            and first["source_name"] == event["source_name"]
        )

    def _is_complete(self) -> bool:
        last = self._lines[-1]["message"].rstrip("\n")
        # Una línea sin indentación (columna 0) que no es el inicio de un
        # traceback es el cierre (la excepción final). Las líneas internas
        # de un traceback van indentadas ("  File …", "    …", carets).
        return last.lstrip() == last and not last.startswith(_TRACEBACK_START)

    def _flush(self) -> Iterable[RawEvent]:
        if not self._lines:
            return
        lines, self._lines = self._lines, []
        first = lines[0]
        severity = max(
            (line.get("severity", Severity.info) for line in lines),
            key=lambda s: _SEVERITY_ORDER.get(s, 1),
        )
        yield RawEvent(
            timestamp=first["timestamp"],
            source_type=first["source_type"],
            source_name=first["source_name"],
            severity=severity,
            message="\n".join(line["message"].rstrip("\n") for line in lines),
            raw="\n".join(line["raw"].rstrip("\n") for line in lines),
        )