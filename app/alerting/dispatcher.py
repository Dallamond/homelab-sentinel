"""Reparte una alerta disparada a los notificadores que la regla pida."""
from __future__ import annotations

import logging

from app.alerting.notifiers.email import EmailNotifier
from app.alerting.notifiers.telegram import TelegramNotifier
from app.db.models import Alert

logger = logging.getLogger(__name__)

_NOTIFIERS = {
    "telegram": TelegramNotifier(),
    "email": EmailNotifier(),
}


async def dispatch(alert: Alert, notify: list[str]) -> dict[str, bool]:
    results: dict[str, bool] = {}
    for channel in notify:
        notifier = _NOTIFIERS.get(channel)
        if notifier is None:
            logger.warning("Notificador desconocido en rules.yaml: %s", channel)
            continue
        results[channel] = await notifier.send(alert)
    return results
