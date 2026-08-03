"""Backend de resúmenes para cualquier API compatible con OpenAI Chat Completions
(OpenAI, OpenRouter, Groq, LM Studio, vLLM, etc.)."""
from __future__ import annotations

import httpx

from app.config import settings


class OpenAICompatSummarizer:
    name = "openai_compat"

    async def summarize(self, prompt: str) -> str:
        if not settings.openai_compat_base_url:
            raise RuntimeError("OPENAI_COMPAT_BASE_URL no configurada")

        url = f"{settings.openai_compat_base_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if settings.openai_compat_api_key:
            headers["Authorization"] = f"Bearer {settings.openai_compat_api_key}"

        payload = {
            "model": settings.openai_compat_model,
            "messages": [{"role": "user", "content": prompt}],
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        return data["choices"][0]["message"]["content"]
