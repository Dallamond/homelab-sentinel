"""
Modelos de la base de datos (SQLAlchemy 2.0 ORM, async).
"""
from __future__ import annotations

import datetime as dt
import enum

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Severity(str, enum.Enum):
    debug = "debug"
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class SourceType(str, enum.Enum):
    journald = "journald"
    docker = "docker"


class LogEvent(Base):
    """Un evento de log normalizado, tal cual llega de un agente."""

    __tablename__ = "log_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    host: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), index=True)
    source_name: Mapped[str] = mapped_column(String(255), index=True)  # unidad systemd o contenedor
    severity: Mapped[Severity] = mapped_column(Enum(Severity), index=True)
    message: Mapped[str] = mapped_column(Text)
    raw: Mapped[str] = mapped_column(Text, default="")


class MonitoredSource(Base):
    """
    Catálogo de fuentes descubiertas automáticamente (unidad systemd o
    contenedor Docker, en un host concreto). El usuario decide desde el
    dashboard cuáles quedan activas para ingesta.
    """

    __tablename__ = "monitored_sources"
    __table_args__ = (UniqueConstraint("host", "source_type", "source_name", name="uq_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    host: Mapped[str] = mapped_column(String(255), index=True)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType))
    source_name: Mapped[str] = mapped_column(String(255))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    first_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    last_seen: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))


class Alert(Base):
    """Una alerta generada por el motor de reglas a partir de uno o varios LogEvents."""

    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    rule_name: Mapped[str] = mapped_column(String(255), index=True)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), index=True)
    host: Mapped[str] = mapped_column(String(255))
    source_name: Mapped[str] = mapped_column(String(255))
    summary: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(Text, default="")
    notified_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_email: Mapped[bool] = mapped_column(Boolean, default=False)


class SummaryReport(Base):
    """Resumen inteligente (semanal/mensual) generado por el summarizer LLM."""

    __tablename__ = "summary_reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    period: Mapped[str] = mapped_column(String(20))  # "weekly" | "monthly"
    period_start: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    backend_used: Mapped[str] = mapped_column(String(50))
    content_md: Mapped[str] = mapped_column(Text)
    stats_json: Mapped[str] = mapped_column(Text)
