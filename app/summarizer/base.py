from __future__ import annotations

from typing import Protocol


class Summarizer(Protocol):
    name: str

    async def summarize(self, prompt: str) -> str:
        """Manda el prompt al backend LLM y devuelve texto en markdown."""
        ...
