"""Back-compat re-export shim for RedisVL vectorizers (#2049 slice 4).

The canonical implementation now lives in ``src.services.vectorizers``.
UserBaseVectorizer (deepvk/USER2-base) was archived in #2627.
New code should import from ``src.services.vectorizers``.

Tracked under #1948 / #2047 / #2049.
"""

from __future__ import annotations

from src.services.vectorizers import BgeM3CacheVectorizer


__all__ = [
    "BgeM3CacheVectorizer",
]
