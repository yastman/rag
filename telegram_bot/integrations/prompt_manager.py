"""Langfuse Prompt Management with caching and graceful degradation.

Fetches versioned prompts from Langfuse with client-side caching.
Falls back to hardcoded prompts when Langfuse is unavailable.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any


logger = logging.getLogger(__name__)

# 1h TTL: prompts change via Langfuse UI deploy, not runtime. Reduces API calls.
DEFAULT_CACHE_TTL = 3600

# Module-level Langfuse client (lazy-initialized singleton)
_langfuse_client: Any | None = None
_langfuse_init_attempted: bool = False
_missing_prompts_until: dict[str, float] = {}
_known_prompts_until: dict[str, float] = {}


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

    if _is_temporarily_missing(name):
        return _apply_fallback_vars(fallback, vars_)

    if not _is_temporarily_known(name):
        available = _probe_prompt_available(client, name)
        if available is False:
            _missing_prompts_until[name] = time.monotonic() + cache_ttl
            logger.debug(
                "Prompt '%s' not found in Langfuse API, using fallback for %ds",
                name,
                cache_ttl,
            )
            return _apply_fallback_vars(fallback, vars_)
        if available is True:
            _known_prompts_until[name] = time.monotonic() + cache_ttl

    try:
        # Do not pass fallback to SDK: for missing prompts SDK logs noisy warnings on each call.
        # We handle fallback ourselves and cache "not found" locally.
        prompt = client.get_prompt(name, cache_ttl_seconds=cache_ttl)
        _missing_prompts_until.pop(name, None)
        if vars_:
            return str(prompt.compile(**vars_))
        return str(prompt.compile())
    except Exception as e:
        if _is_prompt_not_found(e):
            # Avoid hitting Langfuse on every request when prompt/label is absent.
            _missing_prompts_until[name] = time.monotonic() + cache_ttl
            logger.debug(
                "Prompt '%s' not found in Langfuse, using fallback for %ds",
                name,
                cache_ttl,
            )
        else:
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


def _is_prompt_not_found(error: Exception) -> bool:
    """Best-effort detection for Langfuse 404 prompt-not-found errors."""
    text = str(error).lower()
    return (
        "prompt not found" in text or "langfusenotfounderror" in text or "status_code: 404" in text
    )


def _is_temporarily_missing(name: str) -> bool:
    """True when prompt is in local missing-cache TTL window."""
    until = _missing_prompts_until.get(name)
    if until is None:
        return False
    if until > time.monotonic():
        return True
    _missing_prompts_until.pop(name, None)
    return False


def _is_temporarily_known(name: str) -> bool:
    """True when prompt is in local known-available TTL window."""
    until = _known_prompts_until.get(name)
    if until is None:
        return False
    if until > time.monotonic():
        return True
    _known_prompts_until.pop(name, None)
    return False


def _probe_prompt_available(client: Any, name: str) -> bool | None:
    """Probe prompt existence via Langfuse API without triggering SDK warning logs.

    Returns:
        True: prompt exists for target label
        False: prompt not found (404)
        None: probing unavailable/failed, caller may proceed with optimistic fetch
    """
    api = getattr(client, "api", None)
    if api is None or not hasattr(api, "prompts"):
        return None

    label = os.getenv("LANGFUSE_PROMPT_LABEL", "production")

    try:
        api.prompts.get(prompt_name=name, label=label)
        return True
    except Exception as e:
        # Avoid hard dependency on specific SDK exception type at import time.
        status = getattr(e, "status_code", None)
        if status == 404 or _is_prompt_not_found(e):
            return False
        logger.debug("Prompt availability probe failed for '%s': %s", name, e)
        return None


def _reset_client() -> None:
    """Reset the Langfuse client singleton (for testing)."""
    global _langfuse_client, _langfuse_init_attempted
    _langfuse_client = None
    _langfuse_init_attempted = False
    _missing_prompts_until.clear()
    _known_prompts_until.clear()
