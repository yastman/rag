"""Back-compat re-export shim for the BGE-M3 query bundle (#2049 slice 4).

The canonical implementation now lives in ``src.services.bge_m3_query_bundle``.
This module is preserved so existing imports such as

    from telegram_bot.services.bge_m3_query_bundle import BgeM3QueryVectorBundle

continue to resolve. New code should import from ``src.services.bge_m3_query_bundle``.

Tracked under #1948 / #2047 / #2049.
"""

from __future__ import annotations

from src.services.bge_m3_query_bundle import (
    BGE_M3_QUERY_BUNDLE_MAX_LENGTH,
    BGE_M3_QUERY_BUNDLE_MODEL,
    BGE_M3_QUERY_BUNDLE_VERSION,
    BgeM3QueryVectorBundle,
    make_bge_m3_query_bundle_key_material,
)


__all__ = [
    "BGE_M3_QUERY_BUNDLE_MAX_LENGTH",
    "BGE_M3_QUERY_BUNDLE_MODEL",
    "BGE_M3_QUERY_BUNDLE_VERSION",
    "BgeM3QueryVectorBundle",
    "make_bge_m3_query_bundle_key_material",
]
