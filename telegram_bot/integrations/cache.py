"""Back-compat re-export shim for ``CacheLayerManager`` and the 5-tier Redis cache (#2049 slice 4).

The canonical implementation now lives in ``src.runtime.integrations.cache``.
This module is preserved so existing imports such as

    from telegram_bot.integrations.cache import CacheLayerManager
    from telegram_bot.integrations.cache import CACHE_VERSION

continue to resolve. New code should import from ``src.runtime.integrations.cache``.

Tracked under #1948 / #2047 / #2049.
"""

from __future__ import annotations

from src.runtime.integrations.cache import (
    BGE_M3_QUERY_BUNDLE_MODEL_NAME,
    CACHE_VERSION,
    DEFAULT_TTLS,
    SEMANTIC_CACHE_VERSION,
    CacheLayerManager,
    _create_embed_cache,
    _create_semantic_cache,
    _hash,
    _normalize_query_for_cache,
    _redact_redis_credentials,
)


__all__ = [
    "BGE_M3_QUERY_BUNDLE_MODEL_NAME",
    "CACHE_VERSION",
    "DEFAULT_TTLS",
    "SEMANTIC_CACHE_VERSION",
    "CacheLayerManager",
    "_create_embed_cache",
    "_create_semantic_cache",
    "_hash",
    "_normalize_query_for_cache",
    "_redact_redis_credentials",
]
