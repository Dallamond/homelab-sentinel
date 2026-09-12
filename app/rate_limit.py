"""Rate limiter en memoria (ventana deslizante) para endpoints que llaman al LLM."""
from __future__ import annotations

import time
from collections import defaultdict, deque


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        queue = self._hits[key]
        cutoff = now - window_seconds
        while queue and queue[0] < cutoff:
            queue.popleft()
        if len(queue) >= limit:
            return False
        queue.append(now)
        return True


limiter = SlidingWindowLimiter()
