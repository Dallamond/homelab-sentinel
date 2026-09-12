"""
Pipeline central: recibe RawEvent (ya sea desde collectors locales en modo
standalone, o desde la API de ingesta en modo server), lo persiste, lo pasa
por el motor de alertas y despacha notificaciones si corresponde.
"""
from __future__ import annotations

import datetime as dt
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.alerting.dispatcher import dispatch
from app.alerting.engine import AlertEngine, load_rules
from app.collectors.base import RawEvent
from app.config import settings
from app.db.models import Alert, LogEvent

logger = logging.getLogger(__name__)

_engine = AlertEngine(load_rules(settings.rules_path))


def get_engine() -> AlertEngine:
    return _engine


def reload_rules() -> AlertEngine:
    global _engine
    _engine = AlertEngine(load_rules(settings.rules_path))
    return _engine


async def process_event(session: AsyncSession, host: str, event: RawEvent) -> None:
    db_event = LogEvent(
        timestamp=event["timestamp"],
        host=host,
        source_type=event["source_type"],
        source_name=event["source_name"],
        severity=event["severity"],
        message=event["message"],
        raw=event["raw"],
    )
    session.add(db_event)

    fired_rules = _engine.evaluate(event)
    for rule in fired_rules:
        alert = Alert(
            created_at=dt.datetime.now(dt.timezone.utc),
            rule_name=rule.name,
            severity=rule.severity,
            host=host,
            source_name=event["source_name"],
            summary=f"Regla '{rule.name}' disparada por {event['source_name']} ({host}): {event['message'][:200]}",
            details=event["raw"],
        )
        session.add(alert)
        await session.flush()  # para tener alert.id antes de notificar
        logger.warning("ALERTA: %s (%s) en %s/%s", rule.name, rule.severity.value, host, event["source_name"])
        results = await dispatch(alert, rule.notify)
        alert.notified_telegram = results.get("telegram", False)
        alert.notified_email = results.get("email", False)

    await session.commit()
