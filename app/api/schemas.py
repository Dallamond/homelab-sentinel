"""Modelos Pydantic de entrada/salida de la API (separados de los modelos ORM)."""
from __future__ import annotations

import datetime as dt

from pydantic import BaseModel

from app.db.models import Severity, SourceType


class IngestEvent(BaseModel):
    timestamp: dt.datetime
    source_type: SourceType
    source_name: str
    severity: Severity
    message: str
    raw: str = ""


class IngestBatch(BaseModel):
    host: str
    events: list[IngestEvent]


class DiscoveredSource(BaseModel):
    host: str
    source_type: SourceType
    source_name: str


class SourceOut(BaseModel):
    id: int
    host: str
    source_type: SourceType
    source_name: str
    enabled: bool
    first_seen: dt.datetime
    last_seen: dt.datetime

    model_config = {"from_attributes": True}


class AlertOut(BaseModel):
    id: int
    created_at: dt.datetime
    rule_name: str
    severity: Severity
    host: str
    source_name: str
    summary: str
    notified_telegram: bool
    notified_email: bool

    model_config = {"from_attributes": True}


class LogEventOut(BaseModel):
    id: int
    timestamp: dt.datetime
    host: str
    source_type: SourceType
    source_name: str
    severity: Severity
    message: str

    model_config = {"from_attributes": True}


class SummaryOut(BaseModel):
    id: int
    created_at: dt.datetime
    period: str
    period_start: dt.datetime
    period_end: dt.datetime
    backend_used: str
    content_md: str

    model_config = {"from_attributes": True}


class ExplainRequest(BaseModel):
    event_id: int


class ExplainResponse(BaseModel):
    explanation: str
