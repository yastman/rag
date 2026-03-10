"""Throttling (rate limiting) middleware to prevent flood."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Dispatcher
from aiogram.dispatcher.flags import get_flag
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from cachetools import TTLCache  # type: ignore[import-untyped]


logger = logging.getLogger(__name__)

# Defaults when no rate_limit flag is set on the handler
_DEFAULT_MESSAGE_RATE = 1.0
_DEFAULT_CALLBACK_RATE = 0.3
_DEFAULT_KEY = "default"


class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware for per-handler rate limiting via aiogram flags.

    Handlers declare ``flags={"rate_limit": {"rate": 0.3, "key": "catalog_more"}}``
    to get isolated throttle buckets.  Handlers without the flag fall back to
    sensible defaults (1.0 s for messages, 0.3 s for callback queries).

    Uses lazy-created ``TTLCache`` instances keyed by rate value.
    Admins are exempt from rate limiting.
    """

    def __init__(
        self,
        default_rate: float = _DEFAULT_MESSAGE_RATE,
        admin_ids: list[int] | None = None,
    ) -> None:
        """
        Initialize throttling middleware.

        Args:
            default_rate: Default rate limit for messages (seconds).
            admin_ids: List of admin user IDs exempt from throttling.
        """
        self._caches: dict[float, TTLCache[Any, None]] = {}
        self.admin_ids = set(admin_ids or [])
        self.default_rate = default_rate
        logger.info(f"ThrottlingMiddleware initialized: default_rate={default_rate}s")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_cache(self, rate: float) -> TTLCache[Any, None]:
        """Return (or lazily create) a TTLCache for the given *rate*."""
        cache = self._caches.get(rate)
        if cache is None:
            cache = TTLCache(maxsize=10_000, ttl=rate)
            self._caches[rate] = cache
        return cache

    # ------------------------------------------------------------------

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Process event through throttling check."""
        user = data.get("event_from_user")
        if not user:
            return await handler(event, data)

        user_id = user.id

        # Skip throttling for admins
        if user_id in self.admin_ids:
            return await handler(event, data)

        # Resolve rate & key from handler flag or defaults
        rate_config: dict[str, Any] | None = get_flag(data, "rate_limit")

        if rate_config is not None:
            rate: float = float(rate_config.get("rate", self.default_rate))
            key: str = str(rate_config.get("key", _DEFAULT_KEY))
        elif isinstance(event, CallbackQuery):
            rate = _DEFAULT_CALLBACK_RATE
            key = _DEFAULT_KEY
        else:
            rate = self.default_rate
            key = _DEFAULT_KEY

        cache = self._get_cache(rate)
        cache_key = (user_id, key)

        # Check if user is throttled
        if cache_key in cache:
            logger.warning(f"User {user_id} throttled (key={key}, rate={rate}s)")

            if isinstance(event, CallbackQuery):
                await event.answer("Слишком часто, подожди немного", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⏱ Слишком частые запросы. Подождите немного.")

            return None

        # Add to cache
        cache[cache_key] = None
        return await handler(event, data)


def setup_throttling_middleware(
    dp: Dispatcher,
    default_rate: float = _DEFAULT_MESSAGE_RATE,
    admin_ids: list[int] | None = None,
) -> None:
    """
    Setup throttling middleware for bot.

    Args:
        dp: Dispatcher instance
        default_rate: Default rate limit for messages (seconds).
        admin_ids: List of admin user IDs
    """
    middleware = ThrottlingMiddleware(default_rate=default_rate, admin_ids=admin_ids)
    dp.message.middleware.register(middleware)
    dp.callback_query.middleware.register(middleware)
    # Auto-answer callbacks (pre=True) to dismiss Telegram "loading" spinner immediately
    dp.callback_query.middleware.register(CallbackAnswerMiddleware(pre=True))
    logger.info("Throttling middleware registered")
