"""Small in-memory TTL cache for development-time forecast requests."""

import asyncio
import time
from typing import Awaitable, Callable, TypeVar

T = TypeVar("T")


class InMemoryTTLCache:
    """A replaceable cache boundary; Redis can replace this in a later phase."""

    def __init__(self, ttl_seconds: int = 600) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: dict[str, tuple[float, T]] = {}
        self._lock = asyncio.Lock()

    async def get_or_set(self, key: str, factory: Callable[[], Awaitable[T]]) -> T:
        async with self._lock:
            cached = self._entries.get(key)
            if cached and cached[0] > time.monotonic():
                return cached[1]

        value = await factory()
        async with self._lock:
            self._entries[key] = (time.monotonic() + self.ttl_seconds, value)
        return value
