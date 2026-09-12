"""
Persistencia de ajustes editables en la DB + recarga en caliente.

Los overrides guardados en la tabla `settings` ganan a las variables de entorno.
`apply_effective_settings()` los aplica mutando el objeto global `app.config.settings`
(que permite asignación en runtime), igual que `reload_rules()` hace con el motor de
reglas: así notificadores, summarizer y auth del dashboard ven el cambio al instante.

Solo las claves de `EDITABLE_KEYS` (whitelist) pueden tocarse desde la API — el resto
de la configuración sigue viviendo en `.env`. Las de `SECRET_KEYS` nunca vuelven en
claro al frontend (se enmascaran con `mask_secret`).
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.config import Settings, settings
from app.db.models import Setting
from app.db.session import get_session

logger = logging.getLogger(__name__)

# Claves cuyo valor jamás debe volver al frontend en claro.
SECRET_KEYS = frozenset(
    {
        "agent_api_key",
        "dashboard_api_key",
        "telegram_bot_token",
        "smtp_password",
        "gemini_api_key",
        "openai_compat_api_key",
    }
)

# Claves editables desde la GUI de Ajustes. Fuera de aquí se rechaza (422).
EDITABLE_KEYS = frozenset(
    {
        # Summarizer
        "summarizer_backend",
        "gemini_api_key",
        "gemini_model",
        "ollama_base_url",
        "ollama_model",
        "openai_compat_base_url",
        "openai_compat_api_key",
        "openai_compat_model",
        # Telegram
        "telegram_enabled",
        "telegram_bot_token",
        "telegram_chat_id",
        # Email / SMTP
        "email_enabled",
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "smtp_password",
        "email_from",
        "email_to",
        # Seguridad / API
        "dashboard_api_key",
        "agent_api_key",
    }
)

_BOOL_TRUE = {"1", "true", "yes", "on"}


def mask_secret(value: str) -> str:
    """`secret-value-1234` → `••••••••1234`. Vacío → `""`."""
    if not value:
        return ""
    return "•" * 8 + value[-4:]


def _coerce(key: str, raw: str) -> Any:
    """Convierte el string de la DB al tipo del campo en Settings."""
    annotation = settings.model_fields[key].annotation
    if annotation is bool:
        return str(raw).strip().lower() in _BOOL_TRUE
    if annotation is int:
        return int(raw)
    return raw


async def get_overridden_keys() -> list[str]:
    """Claves que tienen un override guardado en la DB (sobre la env var)."""
    async with get_session() as session:
        result = await session.execute(select(Setting))
        return sorted(row.key for row in result.scalars().all())


async def apply_effective_settings() -> list[str]:
    """
    Lee los overrides de la DB y los aplica al objeto global `settings`.
    Devuelve las claves aplicadas. Se llama al arranque (tras `init_db`) y
    después de cada POST /api/settings. Ignora claves fuera de la whitelist.
    """
    async with get_session() as session:
        result = await session.execute(select(Setting))
        rows = {row.key: row.value for row in result.scalars().all()}

    # `settings` es un singleton mutable. Antes de reaplicar los overrides hay
    # que restaurar la base de entorno; de lo contrario, al borrar una fila de
    # la DB el valor anterior quedaría vivo en memoria indefinidamente.
    environment_settings = Settings()
    for key in EDITABLE_KEYS:
        setattr(settings, key, getattr(environment_settings, key))

    applied: list[str] = []
    for key, raw in rows.items():
        if key not in EDITABLE_KEYS:
            logger.warning("Clave de ajuste fuera de whitelist en DB, ignorada: %s", key)
            continue
        try:
            setattr(settings, key, _coerce(key, raw))
        except (ValueError, TypeError) as exc:
            logger.warning("Valor inválido para %s (%r): %s", key, raw, exc)
            continue
        applied.append(key)

    if applied:
        logger.info("Ajustes aplicados en caliente: %s", ", ".join(sorted(applied)))
    return applied


async def save_updates(updates: dict[str, Any]) -> list[str]:
    """
    Guarda los overrides en la DB y los aplica en caliente.

    Semántica por clave:
    - `None`                     → borra el override (vuelve al valor de `.env`).
    - string que empieza por `•` → placeholder enmascarado del frontend: no tocar.
    - cualquier otro valor       → se persiste y se aplica (con coerción de tipo).

    Levanta ValueError si alguna clave no está en EDITABLE_KEYS.
    """
    unknown = [k for k in updates if k not in EDITABLE_KEYS]
    if unknown:
        raise ValueError(f"Claves no editables: {', '.join(sorted(unknown))}")

    async with get_session() as session:
        for key, value in updates.items():
            row = await session.get(Setting, key)

            if value is None:
                if row is not None:
                    await session.delete(row)
                continue

            if isinstance(value, str) and value.startswith("•"):
                continue  # placeholder enmascarado: conservar el valor actual

            stored = str(value)
            if row is None:
                session.add(Setting(key=key, value=stored))
            else:
                row.value = stored
        await session.commit()

    return await apply_effective_settings()