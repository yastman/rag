"""Compatibility shim for runtime grounding policy.

Deprecated: re-export shim for CORE-002. Import from
``src.runtime.grounding.policy`` in new code.
"""

from __future__ import annotations

from src.runtime.grounding.policy import (
    STRICT_GROUNDING_CONFIDENCE_THRESHOLD,
    STRICT_QUERY_TYPES,
    STRICT_TOPICS,
    build_safe_fallback_response,
    get_grounding_mode,
    is_high_risk_grounding_request,
    is_strict_grounding_safe,
    semantic_cache_safe_reuse_allowed,
    should_safe_fallback,
)


__all__ = [
    "STRICT_GROUNDING_CONFIDENCE_THRESHOLD",
    "STRICT_QUERY_TYPES",
    "STRICT_TOPICS",
    "build_safe_fallback_response",
    "get_grounding_mode",
    "is_high_risk_grounding_request",
    "is_strict_grounding_safe",
    "semantic_cache_safe_reuse_allowed",
    "should_safe_fallback",
]
