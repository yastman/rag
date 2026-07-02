"""Throttling (rate limiting) middleware to prevent flood and bound LLM cost."""

from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict
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

# Env-configurable defaults — read once at module import so reload() works in tests
_DEFAULT_CACHE_MAXSIZE: int = int(os.getenv("BOT_THROTTLE_CACHE_MAXSIZE", "10000"))
_DEFAULT_QUERY_QUOTA: int = int(os.getenv("BOT_QUERY_QUOTA", "0"))  # 0 = disabled
_DEFAULT_QUERY_WINDOW: int = int(os.getenv("BOT_QUERY_WINDOW_SECONDS", "60"))


class QuotaTracker:
    """Sliding-window per-user request quota (pure Python, no aiogram dependency).

    Tracks how many requests each user has made within a time window and returns
    True from ``exceeded()`` once the quota is breached.

    Args:
        quota: Maximum number of requests allowed per window. 0 disables the guard.
        window_seconds: Duration of the sliding window in seconds.
        maxsize: Hard cap on the number of tracked users (bounds key growth).

    The per-user timestamp list is pruned on every check (sliding window). The
    key store is an ``OrderedDict`` capped at ``maxsize`` with LRU eviction —
    otherwise a plain dict would leak one key per distinct user ever seen (a
    one-shot user leaves ``[t]`` behind forever, since it is never touched again
    to be pruned).

    ponytail: O(n) prune where n ≤ quota; O(1) LRU touch + evict. Single process,
              CPython GIL prevents data races. Ceiling: if >``maxsize`` users are
              active within one window, the least-recently-active key is evicted —
              a fail-open reset of that user's quota. Upgrade path: per-user
              asyncio.Lock if the GIL is lifted or this moves to a thread pool.
    """

    def __init__(
        self,
        quota: int,
        window_seconds: int,
        maxsize: int = _DEFAULT_CACHE_MAXSIZE,
    ) -> None:
        self.quota = quota
        self.window_seconds = window_seconds
        self._maxsize = maxsize
        # user_id → list[float] of request timestamps within current window.
        # LRU-ordered so idle keys can be evicted once the cap is reached.
        self._counts: OrderedDict[int, list[float]] = OrderedDict()

    def exceeded(self, user_id: int) -> bool:
        """Check and record a request for *user_id*.

        Returns True (and does NOT record) if the quota is exceeded.
        Returns False (and records the timestamp) if the request is allowed.
        """
        if self.quota <= 0:
            return False
        now = time.time()
        cutoff = now - self.window_seconds
        # Prune expired entries (O(n) where n ≤ quota). ``.get`` avoids creating a
        # key on a mere check.
        timestamps = [t for t in self._counts.get(user_id, ()) if t >= cutoff]
        if len(timestamps) >= self.quota:
            self._counts[user_id] = timestamps
            self._counts.move_to_end(user_id)
            return True
        timestamps.append(now)
        self._counts[user_id] = timestamps
        self._counts.move_to_end(user_id)
        # Bound key growth: drop the least-recently-active users past the cap.
        while len(self._counts) > self._maxsize:
            self._counts.popitem(last=False)
        return False

    def reset(self, user_id: int | None = None) -> None:
        """Reset quota counters. If *user_id* is None, clears all users."""
        if user_id is None:
            self._counts.clear()
        else:
            self._counts.pop(user_id, None)


class ThrottlingMiddleware(BaseMiddleware):
    """
    Middleware for per-handler rate limiting via aiogram flags.

    Handlers declare ``flags={"rate_limit": {"rate": 0.3, "key": "catalog_more"}}``
    to get isolated throttle buckets.  Handlers without the flag fall back to
    sensible defaults (1.0 s for messages, 0.3 s for callback queries).

    Uses lazy-created ``TTLCache`` instances keyed by rate value.
    Admins are exempt from rate limiting.

    Additional cost guard:
    ``query_quota`` (env: ``BOT_QUERY_QUOTA``) limits how many requests a user
    may make within ``query_window_seconds`` (env: ``BOT_QUERY_WINDOW_SECONDS``).
    A quota of 0 disables the cost guard entirely.

    TTLCache maxsize is configurable via ``cache_maxsize`` (env:
    ``BOT_THROTTLE_CACHE_MAXSIZE``).  The default is 10 000 for backward
    compatibility.
    """

    def __init__(
        self,
        default_rate: float = _DEFAULT_MESSAGE_RATE,
        admin_ids: list[int] | None = None,
        cache_maxsize: int = _DEFAULT_CACHE_MAXSIZE,
        query_quota: int = _DEFAULT_QUERY_QUOTA,
        query_window_seconds: int = _DEFAULT_QUERY_WINDOW,
    ) -> None:
        """
        Initialize throttling middleware.

        Args:
            default_rate: Default rate limit for messages (seconds).
            admin_ids: List of admin user IDs exempt from throttling.
            cache_maxsize: Maximum number of entries in each TTLCache bucket.
                           Env: BOT_THROTTLE_CACHE_MAXSIZE (default 10 000).
            query_quota: Max LLM requests per user per window. 0 = disabled.
                         Env: BOT_QUERY_QUOTA (default 0).
            query_window_seconds: Sliding-window duration for the quota check.
                                  Env: BOT_QUERY_WINDOW_SECONDS (default 60).
        """
        self._caches: dict[float, TTLCache[Any, None]] = {}
        self.admin_ids = set(admin_ids or [])
        self.default_rate = default_rate
        self._cache_maxsize = cache_maxsize
        self.query_quota = query_quota
        self.query_window_seconds = query_window_seconds
        self._quota_tracker = QuotaTracker(quota=query_quota, window_seconds=query_window_seconds)

        logger.info(
            "ThrottlingMiddleware initialized: default_rate=%ss, "
            "cache_maxsize=%d, query_quota=%d, query_window=%ds",
            default_rate,
            cache_maxsize,
            query_quota,
            query_window_seconds,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_cache(self, rate: float) -> TTLCache[Any, None]:
        """Return (or lazily create) a TTLCache for the given *rate*."""
        cache = self._caches.get(rate)
        if cache is None:
            cache = TTLCache(maxsize=self._cache_maxsize, ttl=rate)
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

        # --- Per-window cost quota check -----------------------------------
        if self._quota_tracker.exceeded(user_id):
            logger.warning(
                "User %d exceeded query quota (%d/%ds)",
                user_id,
                self.query_quota,
                self.query_window_seconds,
            )
            if isinstance(event, CallbackQuery):
                await event.answer("⏱ Превышен лимит запросов. Попробуйте позже.", show_alert=True)
            elif isinstance(event, Message):
                await event.answer("⏱ Вы превысили лимит запросов. Попробуйте позже.")
            return None

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
