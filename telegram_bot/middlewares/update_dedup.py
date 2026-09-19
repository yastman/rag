"""Suppress repeated updates within one bot polling process.

Keep active updates until their handler finishes and the last 10,000 finished
updates for up to 24 hours. This is a bounded transport replay guard, not durable
business-operation idempotency across restarts. Failed/cancelled attempts also
stay recorded: a handler may already have sent a message before raising.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from cachetools import TTLCache


class UpdateDeduplicationMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self._active: set[tuple[int, int]] = set()
        self._finished: TTLCache[tuple[int, int], None] = TTLCache(maxsize=10_000, ttl=86_400)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not isinstance(event, Update):
            return await handler(event, data)
        key = (data["bot"].id, event.update_id)
        if key in self._active or key in self._finished:
            return None
        # No await between checking and claiming: concurrent feeds on this
        # dispatcher cannot enter the downstream dialog lock twice.
        self._active.add(key)
        try:
            return await handler(event, data)
        finally:
            self._finished[key] = None
            self._active.remove(key)
