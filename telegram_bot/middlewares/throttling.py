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


class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware for rate limiting user requests.

    Uses in-memory TTL cache to track user requests.
    Admins are exempt from rate limiting.
    Callback queries (button clicks) and menu buttons use shorter rate limits
    for snappy navigation.  Per-handler rates via aiogram flags (``menu_nav``).
    """

    def __init__(
        self,
        rate_limit: float = 1.5,
        callback_rate_limit: float = 0.3,
        menu_rate_limit: float = 0.3,
        admin_ids: list[int] | None = None,
    ) -> None:
        """
        Initialize throttling middleware.

        Args:
            rate_limit: Time window in seconds for message rate limiting
            callback_rate_limit: Time window in seconds for callback query rate limiting
            menu_rate_limit: Time window in seconds for menu button rate limiting
            admin_ids: List of admin user IDs exempt from throttling
        """
        self.cache: TTLCache[Any, None] = TTLCache(maxsize=10_000, ttl=rate_limit)
        self.callback_cache: TTLCache[Any, None] = TTLCache(maxsize=10_000, ttl=callback_rate_limit)
        self.menu_cache: TTLCache[Any, None] = TTLCache(maxsize=10_000, ttl=menu_rate_limit)
        self.admin_ids = set(admin_ids or [])
        self.rate_limit = rate_limit
        self.callback_rate_limit = callback_rate_limit
        self.menu_rate_limit = menu_rate_limit
        logger.info(
            f"ThrottlingMiddleware initialized: "
            f"msg={rate_limit}s, callback={callback_rate_limit}s, menu={menu_rate_limit}s"
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

        # Route to the right cache based on event type / handler flags
        if isinstance(event, CallbackQuery):
            cache = self.callback_cache
            cache_key = (user_id, event.message.message_id if event.message else 0)
            throttle_type = "callback"
        elif get_flag(data, "menu_nav"):
            # Menu buttons (ReplyKeyboard) — navigation, use short rate limit
            cache = self.menu_cache
            cache_key = user_id
            throttle_type = "menu"
        else:
            cache = self.cache
            cache_key = user_id
            throttle_type = "message"

        # Check if user is throttled
        if cache_key in cache:
            logger.warning(f"User {user_id} throttled ({throttle_type})")

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
    menu_rate_limit: float = 0.3,
    admin_ids: list[int] | None = None,
) -> None:
    """
    Setup throttling middleware for bot.

    Args:
        dp: Dispatcher instance
        rate_limit: Time window in seconds for messages
        callback_rate_limit: Time window in seconds for callback queries
        menu_rate_limit: Time window in seconds for menu buttons
        admin_ids: List of admin user IDs
    """
    middleware = ThrottlingMiddleware(rate_limit, callback_rate_limit, menu_rate_limit, admin_ids)
    dp.message.middleware.register(middleware)
    dp.callback_query.middleware.register(middleware)
    # Auto-answer callbacks (pre=True) to dismiss Telegram "loading" spinner immediately
    dp.callback_query.middleware.register(CallbackAnswerMiddleware(pre=True))
    logger.info("Throttling middleware registered")
