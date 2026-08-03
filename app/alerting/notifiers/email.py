"""Notificador por email vía SMTP (pensado para Gmail + App Password)."""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText

from app.config import settings
from app.db.models import Alert

logger = logging.getLogger(__name__)


class EmailNotifier:
    name = "email"

    async def send(self, alert: Alert) -> bool:
        if not settings.email_enabled or not settings.smtp_user or not settings.email_to:
            logger.debug("Email no configurado, se omite el envío.")
            return False

        subject = f"[homelab-sentinel] {alert.severity.value.upper()} - {alert.rule_name}"
        body = (
            f"Host: {alert.host}\n"
            f"Origen: {alert.source_name}\n"
            f"Severidad: {alert.severity.value}\n\n"
            f"{alert.summary}\n\n---\n{alert.details}"
        )
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.email_from or settings.smtp_user
        msg["To"] = settings.email_to

        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(None, self._send_blocking, msg)
            return True
        except Exception:  # noqa: BLE001
            logger.exception("Fallo enviando alerta por email")
            return False

    def _send_blocking(self, msg: MIMEText) -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)
