"""Backend de resúmenes usando un modelo local vía Ollama."""
from __future__ import annotations

import httpx

from app.config import settings


class OllamaSummarizer:
    name = "ollama"

    async def summarize(self, prompt: str) -> str:
        url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
        payload = {"model": settings.ollama_model, "prompt": prompt, "stream": False}

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()

        return data.get("response", "").strip()
