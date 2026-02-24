"""Throttling (rate limiting) middleware to prevent flood."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from cachetools import TTLCache  # type: ignore[import-untyped]


logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware for rate limiting user requests.

    Uses in-memory TTL cache to track user requests.
    Admins are exempt from rate limiting.
    Callback queries (button clicks) use a shorter rate limit for snappy navigation.
    """

    def __init__(
        self,
        rate_limit: float = 1.5,
        callback_rate_limit: float = 0.3,
        admin_ids: list[int] | None = None,
    ) -> None:
        """
        Initialize throttling middleware.

        Args:
            rate_limit: Time window in seconds for message rate limiting
            callback_rate_limit: Time window in seconds for callback query rate limiting
            admin_ids: List of admin user IDs exempt from throttling
        """
        self.cache = TTLCache(maxsize=10_000, ttl=rate_limit)
        self.callback_cache = TTLCache(maxsize=10_000, ttl=callback_rate_limit)
        self.admin_ids = set(admin_ids or [])
        self.rate_limit = rate_limit
        self.callback_rate_limit = callback_rate_limit
        logger.info(
            f"ThrottlingMiddleware initialized with rate_limit={rate_limit}s, "
            f"callback_rate_limit={callback_rate_limit}s"
        )

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

        # Callbacks: debounce per user+message (different menus don't interfere)
        if isinstance(event, CallbackQuery):
            cache = self.callback_cache
            cache_key = (user_id, event.message.message_id if event.message else 0)
        else:
            cache = self.cache
            cache_key = user_id

        # Check if user is throttled
        if cache_key in cache:
            logger.warning(
                f"User {user_id} throttled (callback={isinstance(event, CallbackQuery)})"
            )

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
    rate_limit: float = 1.5,
    callback_rate_limit: float = 0.3,
    admin_ids: list[int] | None = None,
) -> None:
    """
    Setup throttling middleware for bot.

    Args:
        dp: Dispatcher instance
        rate_limit: Time window in seconds for messages
        callback_rate_limit: Time window in seconds for callback queries
        admin_ids: List of admin user IDs
    """
    middleware = ThrottlingMiddleware(rate_limit, callback_rate_limit, admin_ids)
    dp.message.middleware.register(middleware)
    dp.callback_query.middleware.register(middleware)
    # Auto-answer callbacks (pre=True) to dismiss Telegram "loading" spinner immediately
    dp.callback_query.middleware.register(CallbackAnswerMiddleware(pre=True))
    logger.info("Throttling middleware registered")
