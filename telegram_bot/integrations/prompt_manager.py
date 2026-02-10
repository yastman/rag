"""Langfuse Prompt Management with caching and graceful degradation.

Fetches versioned prompts from Langfuse with client-side caching.
Falls back to hardcoded prompts when Langfuse is unavailable.
"""

from __future__ import annotations

import logging
import os
from typing import Any


logger = logging.getLogger(__name__)

# Default cache TTL in seconds (5 minutes)
DEFAULT_CACHE_TTL = 300

# Module-level Langfuse client (lazy-initialized singleton)
_langfuse_client: Any | None = None
_langfuse_init_attempted: bool = False


def _get_langfuse_client() -> Any | None:
    """Get or create a Langfuse client singleton.

    Returns None if LANGFUSE_SECRET_KEY is not set or initialization fails.
    """
    global _langfuse_client, _langfuse_init_attempted

    if _langfuse_init_attempted:
        return _langfuse_client

    _langfuse_init_attempted = True

    if not os.environ.get("LANGFUSE_SECRET_KEY"):
        logger.debug("Langfuse Prompt Management disabled: LANGFUSE_SECRET_KEY not set")
        return None

    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse()
        logger.info("Langfuse Prompt Management client initialized")
        return _langfuse_client
    except Exception:
        logger.warning("Failed to initialize Langfuse client", exc_info=True)
        return None


def get_prompt(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    variables: dict[str, str] | None = None,
) -> str:
    """Fetch a text prompt from Langfuse with fallback to hardcoded value.

    Args:
        name: Prompt name in Langfuse.
        fallback: Hardcoded fallback prompt used when Langfuse is unavailable.
        cache_ttl: Cache TTL in seconds (default 300).
        variables: Variables for prompt.compile() (e.g. {"domain": "недвижимость"}).

    Returns:
        Compiled prompt string from Langfuse, or the fallback.
    """
    vars_ = variables or {}
    client = _get_langfuse_client()
    if client is None:
        return _apply_fallback_vars(fallback, vars_)

    try:
        prompt = client.get_prompt(name, cache_ttl_seconds=cache_ttl, fallback=fallback)
        if vars_:
            return str(prompt.compile(**vars_))
        return str(prompt.compile())
    except Exception:
        logger.warning("Failed to fetch prompt '%s', using fallback", name, exc_info=True)
        return _apply_fallback_vars(fallback, vars_)


def _apply_fallback_vars(fallback: str, compile_vars: dict[str, str]) -> str:
    """Apply {{var}} substitution on fallback string."""
    if not compile_vars:
        return fallback
    result = fallback
    for key, value in compile_vars.items():
        result = result.replace("{{" + key + "}}", value)
    return result


def _reset_client() -> None:
    """Reset the Langfuse client singleton (for testing)."""
    global _langfuse_client, _langfuse_init_attempted
    _langfuse_client = None
    _langfuse_init_attempted = False
