"""Selecciona la implementación de Summarizer según SUMMARIZER_BACKEND."""
from __future__ import annotations

from app.config import settings
from app.summarizer.base import Summarizer
from app.summarizer.gemini import GeminiSummarizer
from app.summarizer.ollama import OllamaSummarizer
from app.summarizer.openai_compat import OpenAICompatSummarizer


class NullSummarizer:
    name = "none"

    async def summarize(self, prompt: str) -> str:
        return "_Ningún backend de resumen configurado (SUMMARIZER_BACKEND=none)._"


def get_summarizer() -> Summarizer:
    backend = settings.summarizer_backend
    if backend == "gemini":
        return GeminiSummarizer()
    if backend == "ollama":
        return OllamaSummarizer()
    if backend == "openai_compat":
        return OpenAICompatSummarizer()
    return NullSummarizer()
