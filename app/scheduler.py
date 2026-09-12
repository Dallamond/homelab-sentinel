"""Programación de los resúmenes semanales/mensuales vía APScheduler (cron)."""
from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import settings

logger = logging.getLogger(__name__)


async def _run_summary(period: str) -> None:
    from app.db.session import get_session
    from app.reporting import generate_and_store_summary

    try:
        async with get_session() as session:
            await generate_and_store_summary(session, period)
        logger.info("Resumen %s generado por el scheduler", period)
    except Exception:  # noqa: BLE001
        logger.exception("Fallo generando el resumen %s desde el scheduler", period)


def start_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")

    scheduler.add_job(
        _run_summary,
        CronTrigger.from_crontab(settings.weekly_summary_cron),
        kwargs={"period": "weekly"},
        id="weekly_summary",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_summary,
        CronTrigger.from_crontab(settings.monthly_summary_cron),
        kwargs={"period": "monthly"},
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
