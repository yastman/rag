"""Back-compat re-export shim for RedisVL vectorizers (#2049 slice 4).

The canonical implementation now lives in ``src.services.vectorizers``.
This module is preserved so existing imports such as

    from telegram_bot.services.vectorizers import BgeM3CacheVectorizer
    from telegram_bot.services.vectorizers import UserBaseVectorizer

continue to resolve. New code should import from ``src.services.vectorizers``.

Tracked under #1948 / #2047 / #2049.
"""

from __future__ import annotations

from src.services.vectorizers import (
    BgeM3CacheVectorizer,
    UserBaseVectorizer,
)


__all__ = [
    "BgeM3CacheVectorizer",
    "UserBaseVectorizer",
]
