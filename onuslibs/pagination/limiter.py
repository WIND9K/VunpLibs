# -*- coding: utf-8 -*-
import asyncio, time

class RateLimiter:
    """Token-bucket đơn giản cho req_per_sec, dùng cho async."""
    def __init__(self, rps: float) -> None:
        self.rate = max(0.0, rps)
        self.tokens = 1.0
        self.updated = time.perf_counter()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            now = time.perf_counter()
            if self.rate > 0:
                self.tokens = min(1.0, self.tokens + (now - self.updated) * self.rate)
            self.updated = now
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return
            wait_s = (1.0 - self.tokens) / self.rate if self.rate > 0 else 0.0
            await asyncio.sleep(wait_s)
            self.tokens = 0.0
