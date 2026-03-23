from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any


class PollingLockBusy(RuntimeError):
    """Raised when another polling owner is already active."""


@dataclass(slots=True)
class RedisPollingLock:
    redis: Any
    key: str
    ttl_sec: int = 90

    async def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self.redis, method_name)
        result = method(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def acquire(self, owner: str) -> None:
        created = await self._call("set", self.key, owner, ex=self.ttl_sec, nx=True)
        if not created:
            raise PollingLockBusy(
                f"Polling lock {self.key!r} is already held; stop the other bot instance first"
            )

    async def release(self, owner: str) -> None:
        current = await self._call("get", self.key)
        if current == owner:
            await self._call("delete", self.key)
