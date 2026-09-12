"""
Pruebas de conexión reales para el botón "Probar conexión" de Ajustes (A4).

Cada función devuelve `(ok, message)`: `ok` indica si la integración responde
correctamente con la configuración efectiva actual, y `message` es un texto
corto para mostrar en la GUI. Nunca se envían credenciales en el resultado.
"""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_TELEGRAM_SEND = "https://api.telegram.org/bot{token}/sendMessage"
_GEMINI_GENERATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


async def test_telegram() -> tuple[bool, str]:
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False, "Falta TELEGRAM_BOT_TOKEN o CHAT_ID"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                _TELEGRAM_SEND.format(token=token),
                json={
                    "chat_id": chat_id,
                    "text": "✅ Mensaje de prueba de homelab-sentinel",
                },
            )
            resp.raise_for_status()
        return True, "✅ Mensaje de prueba enviado a Telegram"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Test Telegram falló")
        return False, f"Error: {exc}"


async def test_email() -> tuple[bool, str]:
    if not settings.smtp_user:
        return False, "Falta SMTP_USER"
    msg = MIMEText("Mensaje de prueba de homelab-sentinel (sección Ajustes).")
    msg["Subject"] = "[homelab-sentinel] Prueba de conexión"
    msg["From"] = settings.email_from or settings.smtp_user
    msg["To"] = settings.email_to or settings.smtp_user

    def _blocking() -> None:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(msg)

    try:
        await asyncio.get_event_loop().run_in_executor(None, _blocking)
        return True, f"✅ Correo de prueba enviado a {msg['To']}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Test email falló")
        return False, f"Error: {exc}"


async def test_gemini() -> tuple[bool, str]:
    if not settings.gemini_api_key:
        return False, "Falta GEMINI_API_KEY"
    url = _GEMINI_GENERATE.format(model=settings.gemini_model)
    headers = {"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": "Responde solo: OK"}]}]}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                return False, f"HTTP {resp.status_code} ({settings.gemini_model}): {resp.text[:200]}"
        return True, f"✅ Gemini ({settings.gemini_model}) responde OK"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Test Gemini falló")
        return False, f"Error: {exc}"


async def test_ollama() -> tuple[bool, str]:
    url = f"{settings.ollama_base_url.rstrip('/')}/api/tags"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            models = [m.get("name") for m in resp.json().get("models", [])]
        names = ", ".join(models[:5]) if models else "ninguno"
        return True, f"✅ Ollama OK — modelos: {names}"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Test Ollama falló")
        return False, f"Error: {exc}"


async def test_openai_compat() -> tuple[bool, str]:
    if not settings.openai_compat_base_url:
        return False, "Falta OPENAI_COMPAT_BASE_URL"
    url = f"{settings.openai_compat_base_url.rstrip('/')}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if settings.openai_compat_api_key:
        headers["Authorization"] = f"Bearer {settings.openai_compat_api_key}"
    payload = {
        "model": settings.openai_compat_model,
        "messages": [{"role": "user", "content": "Say OK"}],
        "max_tokens": 5,
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
        return True, f"✅ {settings.openai_compat_model} responde OK"
    except Exception as exc:  # noqa: BLE001
        logger.exception("Test openai-compat falló")
        return False, f"Error: {exc}"


async def run(channel: str) -> tuple[bool, str]:
    test = {
        "telegram": test_telegram,
        "email": test_email,
        "gemini": test_gemini,
        "ollama": test_ollama,
        "openai_compat": test_openai_compat,
    }.get(channel)
    if test is None:
        return False, f"Canal de prueba desconocido: {channel}"
    return await test()