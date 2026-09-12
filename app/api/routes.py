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
- /api/rules         (GET)   reglas cargadas
- /api/rules/reload  (POST)  recarga rules.yaml sin reiniciar
- /api/health        (GET)   estado del servicio
"""
from __future__ import annotations

import datetime as dt
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import desc, select

from app.api.schemas import (
    AlertOut,
    DiscoveredSource,
    ExplainRequest,
    ExplainResponse,
    IngestBatch,
    LogEventOut,
    ReloadRulesResponse,
    RuleOut,
    SettingsOut,
    SettingsTestRequest,
    SettingsTestResponse,
    SettingsUpdate,
    SourceOut,
    SummaryOut,
)
from app.config import settings
from app.db.models import Alert, LogEvent, MonitoredSource, SummaryReport
import app.settings_store as settings_store
import app.test_connections as test_connections
from app.db.session import get_session
from app.pipeline import process_event, reload_rules
from app.rate_limit import limiter
from app.reporting import generate_and_store_summary
from app.summarizer.factory import get_summarizer
from app.summarizer.prompts import build_explain_prompt

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_agent_auth(x_agent_key: str | None = Header(default=None)) -> None:
    if settings.role == "agent":
        return
    if settings.agent_api_key and x_agent_key != settings.agent_api_key:
        raise HTTPException(status_code=401, detail="API key de agente inválida")


def _check_dashboard_auth(
    x_dashboard_key: str | None = Header(default=None),
    x_agent_key: str | None = Header(default=None),
) -> None:
    """Protege lectura/escritura del dashboard si DASHBOARD_API_KEY está definida.

    Los agentes autenticados también pueden leer (p. ej. GET /api/sources).
    """
    if not settings.dashboard_api_key:
        return
    if x_dashboard_key == settings.dashboard_api_key:
        return
    if settings.agent_api_key and x_agent_key == settings.agent_api_key:
        return
    raise HTTPException(status_code=401, detail="API key de dashboard inválida")


def _enforce_llm_limit(request: Request, kind: str) -> None:
    if kind == "explain":
        limit = settings.llm_rate_limit_explain
    else:
        limit = settings.llm_rate_limit_summary
    key = f"{kind}:{_client_ip(request)}"
    if not limiter.allow(key, limit, settings.llm_rate_limit_window_seconds):
        raise HTTPException(
            status_code=429,
            detail=f"Demasiadas peticiones de {kind}. Límite: {limit} por hora.",
        )


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "role": settings.role,
        "host": settings.host_name,
        "auth_required": bool(settings.dashboard_api_key),
    }


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
async def register_sources(sources: list[DiscoveredSource]) -> dict:
    now = dt.datetime.now(dt.timezone.utc)
    upserted = 0
    async with get_session() as session:
        for s in sources:
            result = await session.execute(
                select(MonitoredSource).where(
                    MonitoredSource.host == s.host,
                    MonitoredSource.source_type == s.source_type,
                    MonitoredSource.source_name == s.source_name,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.last_seen = now
            else:
                session.add(
                    MonitoredSource(
                        host=s.host,
                        source_type=s.source_type,
                        source_name=s.source_name,
                        enabled=False,
                        first_seen=now,
                        last_seen=now,
                    )
                )
            upserted += 1
        await session.commit()
    return {"upserted": upserted}


@router.get("/sources", response_model=list[SourceOut], dependencies=[Depends(_check_dashboard_auth)])
async def list_sources(host: str | None = None) -> list[SourceOut]:
    async with get_session() as session:
        query = select(MonitoredSource).order_by(MonitoredSource.host, MonitoredSource.source_name)
        if host:
            query = query.where(MonitoredSource.host == host)
        result = await session.execute(query)
        return list(result.scalars().all())


@router.post("/sources/{source_id}/toggle", response_model=SourceOut, dependencies=[Depends(_check_dashboard_auth)])
async def toggle_source(source_id: int) -> SourceOut:
    async with get_session() as session:
        source = await session.get(MonitoredSource, source_id)
        if source is None:
            raise HTTPException(status_code=404, detail="Fuente no encontrada")
        source.enabled = not source.enabled
        await session.commit()
        await session.refresh(source)
        return source


@router.get("/events", response_model=list[LogEventOut], dependencies=[Depends(_check_dashboard_auth)])
async def list_events(limit: int = 100, host: str | None = None, severity: str | None = None) -> list[LogEventOut]:
    async with get_session() as session:
        query = select(LogEvent).order_by(desc(LogEvent.timestamp)).limit(min(limit, 500))
        if host:
            query = query.where(LogEvent.host == host)
        if severity:
            query = query.where(LogEvent.severity == severity)
        result = await session.execute(query)
        return list(result.scalars().all())


@router.get("/alerts", response_model=list[AlertOut], dependencies=[Depends(_check_dashboard_auth)])
async def list_alerts(limit: int = 100) -> list[AlertOut]:
    async with get_session() as session:
        result = await session.execute(select(Alert).order_by(desc(Alert.created_at)).limit(min(limit, 500)))
        return list(result.scalars().all())


@router.get("/summaries", response_model=list[SummaryOut], dependencies=[Depends(_check_dashboard_auth)])
async def list_summaries(period: str | None = None, limit: int = 20) -> list[SummaryOut]:
    async with get_session() as session:
        query = select(SummaryReport).order_by(desc(SummaryReport.created_at)).limit(min(limit, 100))
        if period:
            query = query.where(SummaryReport.period == period)
        result = await session.execute(query)
        return list(result.scalars().all())


@router.post("/summaries/generate", response_model=SummaryOut, dependencies=[Depends(_check_dashboard_auth)])
async def generate_summary_now(request: Request, period: str = "weekly") -> SummaryOut:
    if period not in ("weekly", "monthly"):
        raise HTTPException(status_code=400, detail="period debe ser 'weekly' o 'monthly'")
    _enforce_llm_limit(request, "summary")

    async with get_session() as session:
        try:
            return await generate_and_store_summary(session, period)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Fallo generando resumen")
            raise HTTPException(status_code=502, detail=f"Fallo del backend LLM: {exc}") from exc


@router.post("/explain", response_model=ExplainResponse, dependencies=[Depends(_check_dashboard_auth)])
async def explain_event(payload: ExplainRequest, request: Request) -> ExplainResponse:
    _enforce_llm_limit(request, "explain")
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


@router.get("/rules", response_model=list[RuleOut], dependencies=[Depends(_check_dashboard_auth)])
async def list_rules() -> list[RuleOut]:
    from app.pipeline import get_engine

    return [RuleOut(**item) for item in get_engine().as_dicts()]


@router.post("/rules/reload", response_model=ReloadRulesResponse, dependencies=[Depends(_check_dashboard_auth)])
async def reload_rules_endpoint() -> ReloadRulesResponse:
    engine = reload_rules()
    rules = [RuleOut(**item) for item in engine.as_dicts()]
    return ReloadRulesResponse(loaded=len(rules), rules=rules)


# --- Ajustes (A1-A5) ---


async def _effective_settings() -> SettingsOut:
    """Helper: devuelve los valores efectivos (con secretos enmascarados)."""
    overridden = await settings_store.get_overridden_keys()
    effective: dict = {}
    for key in sorted(settings_store.EDITABLE_KEYS):
        value = getattr(settings, key)
        if key in settings_store.SECRET_KEYS:
            effective[key] = settings_store.mask_secret(str(value))
        else:
            effective[key] = value
    return SettingsOut(
        effective=effective,
        secret_keys=sorted(settings_store.SECRET_KEYS),
        overridden=overridden,
    )


@router.get("/settings", response_model=SettingsOut, dependencies=[Depends(_check_dashboard_auth)])
async def get_settings() -> SettingsOut:
    return await _effective_settings()


@router.post("/settings", response_model=SettingsOut, dependencies=[Depends(_check_dashboard_auth)])
async def update_settings(payload: SettingsUpdate) -> SettingsOut:
    try:
        await settings_store.save_updates(payload.updates)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return await _effective_settings()


@router.post("/settings/test", response_model=SettingsTestResponse, dependencies=[Depends(_check_dashboard_auth)])
async def test_settings_connection(payload: SettingsTestRequest) -> SettingsTestResponse:
    ok, message = await test_connections.run(payload.channel)
    return SettingsTestResponse(ok=ok, message=message)
