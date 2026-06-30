"""Local prompt management — versioned templates only.

All prompt text is owned locally; no runtime calls to external prompt stores.
Replaces the former remote-backed prompt manager (#2628).
"""

from __future__ import annotations

import logging
from typing import Any


logger = logging.getLogger(__name__)

# 1h TTL: accepted for call-site compatibility; not used for lookup.
DEFAULT_CACHE_TTL = 3600


def get_prompt_with_config(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    variables: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(compiled_prompt_text, config_dict)``.

    Config is always empty — model/temperature config lives in local settings.
    """
    return _apply_fallback_vars(fallback, variables or {}), {}


def get_prompt_with_object(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    variables: dict[str, str] | None = None,
) -> tuple[str, None]:
    """Return ``(compiled_prompt_string, None)``.

    The second element is always ``None`` — there is no external prompt object.
    Callers that guard with ``if prompt_obj is not None`` will safely skip
    any prompt-linking path.
    """
    return _apply_fallback_vars(fallback, variables or {}), None


def get_prompt(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    variables: dict[str, str] | None = None,
) -> str:
    """Return the local prompt template with optional variable substitution."""
    return _apply_fallback_vars(fallback, variables or {})


def _apply_fallback_vars(fallback: str, compile_vars: dict[str, str]) -> str:
    """Apply {{var}} substitution on fallback string."""
    if not compile_vars:
        return fallback
    result = fallback
    for key, value in compile_vars.items():
        result = result.replace("{{" + key + "}}", value)
    return result


def _reset_client() -> None:
    """No-op: retained for call-site compatibility (no state to reset)."""
