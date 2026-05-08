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

    async def _call_redis(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        method = getattr(self.redis, method_name, None)
        if method is None:
            return None
        result = method(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    async def _read_busy_diagnostics(self) -> dict[str, Any]:
        diagnostics: dict[str, Any] = {"key": self.key}

        owner = await self._call_redis("get", self.key)
        if owner is not None:
            if isinstance(owner, bytes):
                owner = owner.decode("utf-8", errors="replace")
            diagnostics["owner"] = owner

        pttl = await self._call_redis("pttl", self.key)
        if pttl is not None:
            diagnostics["pttl_ms"] = pttl
        else:
            ttl = await self._call_redis("ttl", self.key)
            if ttl is not None:
                diagnostics["ttl_sec"] = ttl

        return diagnostics

    async def acquire(self, owner: str) -> None:
        self._lock = await self._create_backend_lock()
        created = await self._call("acquire", token=owner)
        if not created:
            self._lock = None
            diagnostics = await self._read_busy_diagnostics()
            raise PollingLockBusy(
                "Polling lock busy"
                f" key={diagnostics.get('key')!r}"
                f" owner={diagnostics.get('owner')!r}"
                f" pttl_ms={diagnostics.get('pttl_ms')!r}"
                f" ttl_sec={diagnostics.get('ttl_sec')!r};"
                " stop the other bot instance first"
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
