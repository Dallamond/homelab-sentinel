"""Notificador vía Telegram Bot API (sin dependencias extra, solo httpx)."""
from __future__ import annotations

import logging

import httpx

from app.config import settings
from app.db.models import Alert

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI = {
    "debug": "🔍",
    "info": "ℹ️",
    "warning": "⚠️",
    "error": "🔴",
    "critical": "🚨",
}


class TelegramNotifier:
    name = "telegram"

    async def send(self, alert: Alert) -> bool:
        if not settings.telegram_enabled or not settings.telegram_bot_token or not settings.telegram_chat_id:
            logger.debug("Telegram no configurado, se omite el envío.")
            return False

        emoji = _SEVERITY_EMOJI.get(alert.severity.value, "")
        text = (
            f"{emoji} *{alert.rule_name}*\n"
            f"Host: `{alert.host}` · Origen: `{alert.source_name}`\n"
            f"{alert.summary}"
        )
        url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
        payload = {"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "Markdown"}

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Fallo enviando alerta por Telegram")
            return False
