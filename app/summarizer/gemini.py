"""Backend de resúmenes usando la API gratuita de Gemini Flash."""
from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiSummarizer:
    name = "gemini"

    async def summarize(self, prompt: str) -> str:
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY no configurada")

        url = _ENDPOINT.format(model=settings.gemini_model)
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        headers = {"x-goog-api-key": settings.gemini_api_key, "Content-Type": "application/json"}

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code != 200:
                body = resp.text[:500]
                raise RuntimeError(
                    f"Gemini API devolvió HTTP {resp.status_code} "
                    f"(modelo='{settings.gemini_model}'): {body}"
                )
            data = resp.json()

        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            logger.error("Respuesta inesperada de Gemini: %s", data)
            raise RuntimeError("No se pudo extraer el texto de la respuesta de Gemini")
