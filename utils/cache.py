"""Redis cache helpers (skeleton)."""
from typing import Optional


class CacheBackend:
    def __init__(self) -> None:  # placeholder; integrate aioredis later
        self._mem: dict[str, str] = {}

    async def get(self, key: str) -> Optional[str]:
        return self._mem.get(key)

    async def set(self, key: str, value: str, ttl_seconds: int = 900) -> None:  # noqa: ARG002
        self._mem[key] = value


cache_backend = CacheBackend()