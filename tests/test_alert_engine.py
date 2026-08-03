"""Tests del motor de reglas: umbral, ventana deslizante y cooldown."""
from __future__ import annotations

import datetime as dt
import re


from app.alerting.engine import AlertEngine, Rule
from app.db.models import Severity, SourceType


def _event(msg: str, when: dt.datetime, severity: Severity = Severity.error):
    return {
        "timestamp": when,
        "source_type": SourceType.journald,
        "source_name": "test.service",
        "severity": severity,
        "message": msg,
        "raw": msg,
    }


def _make_rule(**overrides) -> Rule:
    defaults = dict(
        name="test-rule",
        pattern=re.compile("boom", re.IGNORECASE),
        min_severity=Severity.warning,
        source_type="any",
        threshold=3,
        window_seconds=60,
        cooldown_seconds=300,
        severity=Severity.error,
        notify=[],
    )
    defaults.update(overrides)
    return Rule(**defaults)


def test_rule_does_not_fire_below_threshold():
    rule = _make_rule(threshold=3)
    engine = AlertEngine([rule])
    now = dt.datetime.now(dt.timezone.utc)

    fired = []
    for i in range(2):
        fired += engine.evaluate(_event("boom happened", now + dt.timedelta(seconds=i)))

    assert fired == []


def test_rule_fires_once_threshold_reached():
    rule = _make_rule(threshold=3)
    engine = AlertEngine([rule])
    now = dt.datetime.now(dt.timezone.utc)

    fired = []
    for i in range(3):
        fired += engine.evaluate(_event("boom happened", now + dt.timedelta(seconds=i)))

    assert len(fired) == 1
    assert fired[0].name == "test-rule"


def test_rule_respects_cooldown():
    rule = _make_rule(threshold=1, cooldown_seconds=600)
    engine = AlertEngine([rule])
    now = dt.datetime.now(dt.timezone.utc)

    first = engine.evaluate(_event("boom", now))
    second = engine.evaluate(_event("boom", now + dt.timedelta(seconds=10)))

    assert len(first) == 1
    assert second == []  # dentro del cooldown, no debe volver a disparar


def test_rule_ignores_events_below_min_severity():
    rule = _make_rule(threshold=1, min_severity=Severity.error)
    engine = AlertEngine([rule])
    now = dt.datetime.now(dt.timezone.utc)

    fired = engine.evaluate(_event("boom", now, severity=Severity.info))
    assert fired == []


def test_rule_ignores_non_matching_message():
    rule = _make_rule(threshold=1)
    engine = AlertEngine([rule])
    now = dt.datetime.now(dt.timezone.utc)

    fired = engine.evaluate(_event("everything is fine", now))
    assert fired == []


def test_window_expires_old_hits():
    rule = _make_rule(threshold=2, window_seconds=5)
    engine = AlertEngine([rule])
    now = dt.datetime.now(dt.timezone.utc)

    engine.evaluate(_event("boom", now))
    fired = engine.evaluate(_event("boom", now + dt.timedelta(seconds=10)))  # fuera de ventana

    assert fired == []
