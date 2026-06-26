"""Observability re-exports — tracing removed (#2844, #2969).

Re-exports the non-tracing helpers from :mod:`src.observability` for
backward-compatible import paths used across ``telegram_bot``.
"""

from src.observability import mask_pii, propagate_attributes


__all__ = [
    "mask_pii",
    "propagate_attributes",
]
