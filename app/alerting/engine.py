"""
Motor de reglas: mantiene una ventana deslizante de eventos recientes por
regla y decide cuándo se dispara una alerta, respetando el cooldown para no
saturar los notificadores.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from app.collectors.base import RawEvent
from app.db.models import Severity

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = [Severity.debug, Severity.info, Severity.warning, Severity.error, Severity.critical]


def _severity_at_least(value: Severity, minimum: Severity) -> bool:
    return _SEVERITY_ORDER.index(value) >= _SEVERITY_ORDER.index(minimum)


@dataclass
class Rule:
    name: str
    pattern: re.Pattern
    min_severity: Severity
    source_type: str  # "journald" | "docker" | "any"
    threshold: int
    window_seconds: int
    cooldown_seconds: int
    severity: Severity
    notify: list[str]
    _hits: deque = field(default_factory=deque)
    _last_fired: dt.datetime | None = field(default=None)

    def matches(self, event: RawEvent) -> bool:
        if self.source_type != "any" and event["source_type"].value != self.source_type:
            return False
        if not _severity_at_least(event["severity"], self.min_severity):
            return False
        return bool(self.pattern.search(event["message"]))

    def register_and_check(self, event: RawEvent) -> bool:
        """Registra el hit y devuelve True si la regla debe disparar una alerta ahora."""
        now = event["timestamp"]
        self._hits.append(now)
        window_start = now - dt.timedelta(seconds=self.window_seconds)
        while self._hits and self._hits[0] < window_start:
            self._hits.popleft()

        if len(self._hits) < self.threshold:
            return False

        if self._last_fired is not None:
            cooldown_end = self._last_fired + dt.timedelta(seconds=self.cooldown_seconds)
            if now < cooldown_end:
                return False

        self._last_fired = now
        return True


def load_rules(path: Path) -> list[Rule]:
    if not path.exists():
        logger.warning("No se encontró rules.yaml en %s, no habrá reglas activas.", path)
        return []

    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules: list[Rule] = []
    for item in raw.get("rules", []):
        rules.append(
            Rule(
                name=item["name"],
                pattern=re.compile(item["match"], re.IGNORECASE),
                min_severity=Severity(item.get("min_severity", "info")),
                source_type=item.get("source_type", "any"),
                threshold=int(item.get("threshold", 1)),
                window_seconds=int(item.get("window_seconds", 60)),
                cooldown_seconds=int(item.get("cooldown_seconds", 600)),
                severity=Severity(item.get("severity", "warning")),
                notify=item.get("notify", []),
            )
        )
    logger.info("Cargadas %d reglas de alerta desde %s", len(rules), path)
    return rules


class AlertEngine:
    """Evalúa cada evento entrante contra todas las reglas cargadas."""

    def __init__(self, rules: list[Rule]) -> None:
        self.rules = rules

    def evaluate(self, event: RawEvent) -> list[Rule]:
        fired: list[Rule] = []
        for rule in self.rules:
            if rule.matches(event) and rule.register_and_check(event):
                fired.append(rule)
        return fired

    def as_dicts(self) -> list[dict]:
        return [
            {
                "name": rule.name,
                "match": rule.pattern.pattern,
                "min_severity": rule.min_severity.value,
                "source_type": rule.source_type,
                "threshold": rule.threshold,
                "window_seconds": rule.window_seconds,
                "cooldown_seconds": rule.cooldown_seconds,
                "severity": rule.severity.value,
                "notify": list(rule.notify),
            }
            for rule in self.rules
        ]
