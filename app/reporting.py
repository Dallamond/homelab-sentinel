"""
Agregación de estadísticas para los resúmenes periódicos: cuenta eventos por
severidad/host/origen, identifica los orígenes más ruidosos y arma el
contexto (JSON) que se manda al LLM.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Alert, LogEvent, Severity, SummaryReport
from app.summarizer.factory import get_summarizer
from app.summarizer.prompts import build_period_summary_prompt

logger = logging.getLogger(__name__)


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


async def generate_and_store_summary(session: AsyncSession, period: str) -> SummaryReport:
    if period not in ("weekly", "monthly"):
        raise ValueError("period debe ser 'weekly' o 'monthly'")

    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=7 if period == "weekly" else 30)
    stats = await build_period_stats(session, start, end)
    prompt = build_period_summary_prompt(period, stats)
    summarizer = get_summarizer()
    content_md = await summarizer.summarize(prompt)

    report = SummaryReport(
        created_at=end,
        period=period,
        period_start=start,
        period_end=end,
        backend_used=summarizer.name,
        content_md=content_md,
        stats_json=json.dumps(stats, default=str),
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report
