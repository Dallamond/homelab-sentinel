"""
Endpoints de la API:

- /api/ingest        (POST)  agentes remotos suben lotes de eventos
- /api/sources       (GET)   catálogo de fuentes descubiertas
- /api/sources/register (POST) agentes registran/actualizan lo que ven
- /api/sources/{id}/toggle (POST) el usuario activa/desactiva una fuente desde el dashboard
- /api/events        (GET)   últimos eventos (para el feed en vivo)
- /api/alerts        (GET)   histórico de alertas
- /api/summaries     (GET)   resúmenes generados
- /api/summaries/generate (POST) fuerza la generación de un resumen ahora
- /api/explain       (POST)  pide al LLM que explique un evento concreto
- /api/health        (GET)   estado del servicio
"""
from __future__ import annotations

import datetime as dt
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import desc, select

from app.api.schemas import (
    AlertOut,
    ExplainRequest,
    ExplainResponse,
    IngestBatch,
    LogEventOut,
    SourceOut,
    SummaryOut,
)
from app.config import settings
from app.db.models import Alert, LogEvent, MonitoredSource, SummaryReport
from app.db.session import get_session
from app.pipeline import process_event
from app.reporting import build_period_stats
from app.summarizer.factory import get_summarizer
from app.summarizer.prompts import build_explain_prompt, build_period_summary_prompt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _check_agent_auth(x_agent_key: str | None = Header(default=None)) -> None:
    if settings.role == "agent":
        return  # un agente no expone esta API
    if settings.agent_api_key and x_agent_key != settings.agent_api_key:
        raise HTTPException(status_code=401, detail="API key de agente inválida")


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "role": settings.role, "host": settings.host_name}


@router.post("/ingest", dependencies=[Depends(_check_agent_auth)])
async def ingest(batch: IngestBatch) -> dict:
    async with get_session() as session:
        for item in batch.events:
            raw_event = {
                "timestamp": item.timestamp,
                "source_type": item.source_type,
                "source_name": item.source_name,
                "severity": item.severity,
                "message": item.message,
                "raw": item.raw,
            }
            await process_event(session, batch.host, raw_event)
    return {"ingested": len(batch.events)}


@router.post("/sources/register", dependencies=[Depends(_check_agent_auth)])
async def register_sources(sources: list[dict]) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    upserted = 0
    async with get_session() as session:
        for s in sources:
            result = await session.execute(
                select(MonitoredSource).where(
                    MonitoredSource.host == s["host"],
                    MonitoredSource.source_type == s["source_type"],
                    MonitoredSource.source_name == s["source_name"],
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.last_seen = now
            else:
                session.add(
                    MonitoredSource(
                        host=s["host"],
                        source_type=s["source_type"],
                        source_name=s["source_name"],
                        enabled=False,
                        first_seen=now,
                        last_seen=now,
                    )
                )
            upserted += 1
        await session.commit()
    return {"upserted": upserted}


@router.get("/sources", response_model=list[SourceOut])
async def list_sources(host: str | None = None) -> list[SourceOut]:
    async with get_session() as session:
        query = select(MonitoredSource).order_by(MonitoredSource.host, MonitoredSource.source_name)
        if host:
            query = query.where(MonitoredSource.host == host)
        result = await session.execute(query)
        return list(result.scalars().all())


@router.post("/sources/{source_id}/toggle", response_model=SourceOut)
async def toggle_source(source_id: int) -> SourceOut:
    async with get_session() as session:
        source = await session.get(MonitoredSource, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Fuente no encontrada")
        source.enabled = not source.enabled
        await session.commit()
        await session.refresh(source)
        return source


@router.get("/events", response_model=list[LogEventOut])
async def list_events(limit: int = 100, host: str | None = None, severity: str | None = None) -> list[LogEventOut]:
    async with get_session() as session:
        query = select(LogEvent).order_by(desc(LogEvent.timestamp)).limit(min(limit, 500))
        if host:
            query = query.where(LogEvent.host == host)
        if severity:
            query = query.where(LogEvent.severity == severity)
        result = await session.execute(query)
        return list(result.scalars().all())


@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(limit: int = 100) -> list[AlertOut]:
    async with get_session() as session:
        result = await session.execute(select(Alert).order_by(desc(Alert.created_at)).limit(min(limit, 500)))
        return list(result.scalars().all())


@router.get("/summaries", response_model=list[SummaryOut])
async def list_summaries(period: str | None = None, limit: int = 20) -> list[SummaryOut]:
    async with get_session() as session:
        query = select(SummaryReport).order_by(desc(SummaryReport.created_at)).limit(min(limit, 100))
        if period:
            query = query.where(SummaryReport.period == period)
        result = await session.execute(query)
        return list(result.scalars().all())


@router.post("/summaries/generate", response_model=SummaryOut)
async def generate_summary_now(period: str = "weekly") -> SummaryOut:
    if period not in ("weekly", "monthly"):
        raise HTTPException(status_code=400, detail="period debe ser 'weekly' o 'monthly'")

    end = dt.datetime.now(dt.timezone.utc)
    start = end - dt.timedelta(days=7 if period == "weekly" else 30)

    async with get_session() as session:
        stats = await build_period_stats(session, start, end)
        prompt = build_period_summary_prompt(period, stats)
        summarizer = get_summarizer()
        try:
            content_md = await summarizer.summarize(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fallo generando resumen con backend %s", summarizer.name)
            raise HTTPException(status_code=502, detail=f"Fallo del backend LLM: {exc}") from exc

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


@router.post("/explain", response_model=ExplainResponse)
async def explain_event(payload: ExplainRequest) -> ExplainResponse:
    async with get_session() as session:
        event = await session.get(LogEvent, payload.event_id)
        if event is None:
            raise HTTPException(status_code=404, detail="Evento no encontrado")

        prompt = build_explain_prompt(event.source_name, event.severity.value, event.message, event.raw)
        summarizer = get_summarizer()
        try:
            explanation = await summarizer.summarize(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fallo explicando evento con backend %s", summarizer.name)
            raise HTTPException(status_code=502, detail=f"Fallo del backend LLM: {exc}") from exc

        return ExplainResponse(explanation=explanation)
