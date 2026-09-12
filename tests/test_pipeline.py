"""Tests del pipeline central: process_event, persistencia, alertas, hot-reload."""
from __future__ import annotations

import datetime as dt
import os

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_sentinel_pipeline.db")
os.environ.setdefault("SUMMARIZER_BACKEND", "none")

import pytest
from sqlalchemy import select

from app.db.models import Alert, LogEvent, Severity, SourceType
from app.db.session import engine, get_session
from app.pipeline import get_engine, process_event, reload_rules
from app.collectors.base import RawEvent


@pytest.fixture(scope="module", autouse=True)
def _init_db():
    import asyncio

    from app.db.models import Base

    async def _reset():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_reset())


@pytest.fixture
async def session():
    async with get_session() as s:
        yield s


class TestProcessEvent:
    @pytest.mark.asyncio
    async def test_process_event_persists_log_event(self, session):
        event: RawEvent = {
            "timestamp": dt.datetime.now(dt.timezone.utc),
            "source_type": SourceType.journald,
            "source_name": "test.service",
            "severity": Severity.info,
            "message": "pipeline test message",
            "raw": "pipeline test message",
        }
        await process_event(session, "test-host", event)

        result = await session.execute(select(LogEvent).where(LogEvent.host == "test-host"))
        events = list(result.scalars().all())
        assert len(events) == 1
        assert events[0].message == "pipeline test message"
        assert events[0].host == "test-host"
        assert events[0].source_type == SourceType.journald
        assert events[0].severity == Severity.info

    @pytest.mark.asyncio
    async def test_process_event_fires_alert_on_rule_match(self, session):
        # Need a rule that matches; use the "Fallo repetido de servicio" rule
        # which matches "failed" or "error" with threshold=5
        # We'll send 5 matching events
        engine = get_engine()
        rules = engine.rules
        # Find the rule we want
        target_rule = next((r for r in rules if r.name == "Fallo repetido de servicio"), None)
        assert target_rule is not None, "Rule 'Fallo repetido de servicio' not found in rules.yaml"

        # Ensure it's configured to fire on 5 errors
        assert target_rule.threshold == 5
        assert target_rule.min_severity == Severity.error

        now = dt.datetime.now(dt.timezone.utc)
        for i in range(5):
            event: RawEvent = {
                "timestamp": now + dt.timedelta(seconds=i),
                "source_type": SourceType.journald,
                "source_name": "test.service",
                "severity": Severity.error,
                "message": f"failed attempt {i}",
                "raw": f"failed attempt {i}",
            }
            await process_event(session, "alert-test-host", event)

        # Check alert was created
        result = await session.execute(select(Alert).where(Alert.rule_name == "Fallo repetido de servicio"))
        alerts = list(result.scalars().all())
        assert len(alerts) == 1
        assert alerts[0].severity == Severity.error
        assert alerts[0].host == "alert-test-host"

    @pytest.mark.asyncio
    async def test_process_event_respects_cooldown(self, session):
        # Send 5 events to fire once, then 5 more within cooldown -> no second alert
        engine = get_engine()
        target_rule = next((r for r in engine.rules if r.name == "Fallo repetido de servicio"), None)
        assert target_rule is not None

        now = dt.datetime.now(dt.timezone.utc)
        # First batch of 5
        for i in range(5):
            event: RawEvent = {
                "timestamp": now + dt.timedelta(seconds=i),
                "source_type": SourceType.journald,
                "source_name": "cooldown-test.service",
                "severity": Severity.error,
                "message": f"failed {i}",
                "raw": f"failed {i}",
            }
            await process_event(session, "cooldown-host", event)

        # Second batch of 5, but within cooldown (cooldown=1800s)
        for i in range(5, 10):
            event: RawEvent = {
                "timestamp": now + dt.timedelta(seconds=i),
                "source_type": SourceType.journald,
                "source_name": "cooldown-test.service",
                "severity": Severity.error,
                "message": f"failed {i}",
                "raw": f"failed {i}",
            }
            await process_event(session, "cooldown-host", event)

        result = await session.execute(select(Alert).where(Alert.rule_name == "Fallo repetido de servicio"))
        alerts = list(result.scalars().all())
        # Should only have 1 alert (the second batch should be suppressed by cooldown)
        assert len(alerts) == 1


class TestHotReload:
    @pytest.mark.asyncio
    async def test_reload_rules_returns_new_engine(self, session):
        old_engine = get_engine()
        old_rules_count = len(old_engine.rules)

        new_engine = reload_rules()
        assert new_engine is not old_engine
        assert len(new_engine.rules) == old_rules_count

        # Verify engine is accessible via get_engine
        assert get_engine() is new_engine

    @pytest.mark.asyncio
    async def test_reload_rules_reflects_yaml_changes(self, session, tmp_path):
        # Create a temporary rules file with one extra rule
        import yaml

        rules_file = tmp_path / "test_rules.yaml"
        rules_content = {
            "rules": [
                {
                    "name": "Temp Test Rule",
                    "match": "temp match",
                    "min_severity": "info",
                    "source_type": "any",
                    "threshold": 1,
                    "window_seconds": 60,
                    "cooldown_seconds": 300,
                    "severity": "warning",
                    "notify": [],
                }
            ]
        }
        rules_file.write_text(yaml.dump(rules_content), encoding="utf-8")

        # Temporarily swap settings.rules_path
        from app.config import settings
        original_path = settings.rules_path
        try:
            settings.rules_path = rules_file
            new_engine = reload_rules()
            rule_names = [r.name for r in new_engine.rules]
            assert "Temp Test Rule" in rule_names
        finally:
            settings.rules_path = original_path
            reload_rules()  # restore