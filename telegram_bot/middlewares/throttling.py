"""Throttling (rate limiting) middleware to prevent flood."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Dispatcher
from aiogram.types import CallbackQuery, Message, TelegramObject
from cachetools import TTLCache


logger = logging.getLogger(__name__)


class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware for rate limiting user requests.

    Uses in-memory TTL cache to track user requests.
    Admins are exempt from rate limiting.
    """

    def __init__(self, rate_limit: float = 1.5, admin_ids: list[int] | None = None) -> None:
        """
        Initialize throttling middleware.

        Args:
            rate_limit: Time window in seconds for rate limiting
            admin_ids: List of admin user IDs exempt from throttling
        """
        self.cache = TTLCache(maxsize=10_000, ttl=rate_limit)
        self.admin_ids = set(admin_ids or [])
        self.rate_limit = rate_limit
        logger.info(f"ThrottlingMiddleware initialized with rate_limit={rate_limit}s")

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

        # Check if user is throttled
        if user_id in self.cache:
            logger.warning(f"User {user_id} throttled")

            if isinstance(event, CallbackQuery):
                await event.answer("Слишком часто, подожди немного", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⏱ Слишком частые запросы. Подождите немного.")

            return None

        # Add user to cache
        self.cache[user_id] = None
        return await handler(event, data)


def setup_throttling_middleware(
    dp: Dispatcher, rate_limit: float = 1.5, admin_ids: list[int] | None = None
) -> None:
    """
    Setup throttling middleware for bot.

    Args:
        dp: Dispatcher instance
        rate_limit: Time window in seconds
        admin_ids: List of admin user IDs
    """
    middleware = ThrottlingMiddleware(rate_limit, admin_ids)
    dp.message.middleware.register(middleware)
    dp.callback_query.middleware.register(middleware)
    logger.info("Throttling middleware registered")
