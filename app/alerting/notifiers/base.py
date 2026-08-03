from __future__ import annotations

from typing import Protocol

from app.db.models import Alert


class Notifier(Protocol):
    name: str

    async def send(self, alert: Alert) -> bool:
        """Devuelve True si se envió correctamente."""
        ...
