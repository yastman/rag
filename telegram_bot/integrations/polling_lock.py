from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any


class PollingLockBusy(RuntimeError):
    """Raised when another polling owner is already active."""


@dataclass(slots=True)
class RedisPollingLock:
    redis: Any
    key: str
    ttl_sec: int = 90
    _lock: Any | None = field(init=False, default=None, repr=False)

    async def _call(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self._lock, method_name)
        result = method(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _create_backend_lock(self) -> Any:
        result = self.redis.lock(
            self.key,
            timeout=self.ttl_sec,
            blocking=False,
            thread_local=False,
        )
        if inspect.isawaitable(result):
            return await result
        return result

    async def acquire(self, owner: str) -> None:
        self._lock = await self._create_backend_lock()
        created = await self._call("acquire", token=owner)
        if not created:
            self._lock = None
            raise PollingLockBusy(
                f"Polling lock {self.key!r} is already held; stop the other bot instance first"
            )

    async def refresh(self) -> None:
        if self._lock is None:
            raise RuntimeError("Polling lock is not acquired")
        await self._call("reacquire")

    async def release(self) -> None:
        if self._lock is None:
            return
        try:
            await self._call("release")
        finally:
            self._lock = None
