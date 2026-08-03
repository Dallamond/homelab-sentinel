"""Programación de los resúmenes semanales/mensuales vía APScheduler (cron)."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger(__name__)


def start_scheduler() -> AsyncIOScheduler:
    from app.api.routes import generate_summary_now  # import diferido, evita ciclos

    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        lambda: generate_summary_now(period="weekly"),
        CronTrigger.from_crontab(settings.weekly_summary_cron),
        id="weekly_summary",
        replace_existing=True,
    )
    scheduler.add_job(
        lambda: generate_summary_now(period="monthly"),
        CronTrigger.from_crontab(settings.monthly_summary_cron),
        id="monthly_summary",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler arrancado: weekly='%s' monthly='%s'",
        settings.weekly_summary_cron,
        settings.monthly_summary_cron,
    )
    return scheduler
