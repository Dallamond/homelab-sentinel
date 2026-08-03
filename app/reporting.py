"""
Agregación de estadísticas para los resúmenes periódicos: cuenta eventos por
severidad/host/origen, identifica los orígenes más ruidosos y arma el
contexto (JSON) que se manda al LLM.
"""
from __future__ import annotations

import datetime as dt
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, LogEvent, Severity


async def build_period_stats(session: AsyncSession, start: dt.datetime, end: dt.datetime) -> dict:
    events_result = await session.execute(
        select(LogEvent).where(LogEvent.timestamp >= start, LogEvent.timestamp < end)
    )
    events = events_result.scalars().all()

    alerts_result = await session.execute(
        select(Alert).where(Alert.created_at >= start, Alert.created_at < end)
    )
    alerts = alerts_result.scalars().all()

    severity_counts = Counter(e.severity.value for e in events)
    source_counts = Counter(f"{e.host}/{e.source_name}" for e in events)
    top_sources = source_counts.most_common(10)

    return {
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "total_events": len(events),
        "events_by_severity": dict(severity_counts),
        "top_noisy_sources": top_sources,
        "total_alerts": len(alerts),
        "alerts": [
            {
                "rule": a.rule_name,
                "severity": a.severity.value,
                "host": a.host,
                "source": a.source_name,
                "summary": a.summary,
                "created_at": a.created_at.isoformat(),
            }
            for a in alerts
        ],
        "critical_or_error_events_sample": [
            {"host": e.host, "source": e.source_name, "message": e.message}
            for e in events
            if e.severity in (Severity.error, Severity.critical)
        ][:25],
    }
