"""Langfuse Prompt Management with caching and graceful degradation.

Fetches versioned prompts from Langfuse with client-side caching.
Falls back to hardcoded prompts when Langfuse is unavailable.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

# 1h TTL: prompts change via Langfuse UI deploy, not runtime. Reduces API calls.
DEFAULT_CACHE_TTL = 3600

# Module-level TTL caches for prompt existence
_missing_prompts_until: dict[str, float] = {}
_known_prompts_until: dict[str, float] = {}


def get_prompt_with_config(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = DEFAULT_CACHE_TTL,
    variables: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Fetch prompt text and config dict from Langfuse.

    Config may contain temperature, max_tokens, model, etc. — editable in Langfuse UI.

    Returns:
        Tuple of (compiled_prompt_text, config_dict).
        Returns empty dict for config when using fallback.
    """
    return _fetch_prompt_core(name, fallback=fallback, cache_ttl=cache_ttl, variables=variables)


@observe(name="get-prompt", capture_input=False, capture_output=False)
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
        cache_ttl: Cache TTL in seconds (default 3600).
        variables: Variables for prompt.compile() (e.g. {"domain": "недвижимость"}).

    Returns:
        Compiled prompt string from Langfuse, or the fallback.
    """
    text, _ = _fetch_prompt_core(name, fallback=fallback, cache_ttl=cache_ttl, variables=variables)
    return text


def _fetch_prompt_core(
    name: str,
    *,
    fallback: str,
    cache_ttl: int,
    variables: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Core prompt fetcher returning (text, config) tuple."""
    vars_ = variables or {}

    def _fallback_result() -> tuple[str, dict[str, Any]]:
        return _apply_fallback_vars(fallback, vars_), {}

    client = get_client()
    if client is None:
        return _fallback_result()

    if _is_temporarily_missing(name):
        return _fallback_result()

    if not _is_temporarily_known(name):
        available = _probe_prompt_available(client, name)
        if available is False:
            _missing_prompts_until[name] = time.monotonic() + cache_ttl
            logger.debug(
                "Prompt '%s' not found in Langfuse API, using fallback for %ds",
                name,
                cache_ttl,
            )
            return _fallback_result()
        if available is True:
            _known_prompts_until[name] = time.monotonic() + cache_ttl

    try:
        prompt = client.get_prompt(name, cache_ttl_seconds=cache_ttl)
        _missing_prompts_until.pop(name, None)
        config: dict[str, Any] = getattr(prompt, "config", None) or {}
        if vars_:
            return str(prompt.compile(**vars_)), config
        return str(prompt.compile()), config
    except Exception as e:
        if _is_prompt_not_found(e):
            _missing_prompts_until[name] = time.monotonic() + cache_ttl
            logger.debug(
                "Prompt '%s' not found in Langfuse, using fallback for %ds",
                name,
                cache_ttl,
            )
            return _fallback_result()

        logger.warning("Failed to fetch prompt '%s', using fallback", name, exc_info=True)
        return _fallback_result()


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
    """Probe prompt existence via Langfuse API without triggering SDK warning logs."""
    api = getattr(client, "api", None)
    if api is None or not hasattr(api, "prompts"):
        return None

    label = os.getenv("LANGFUSE_PROMPT_LABEL", "production")

    try:
        api.prompts.get(prompt_name=name, label=label)
        return True
    except Exception as e:
        status = getattr(e, "status_code", None)
        if status == 404 or _is_prompt_not_found(e):
            return False
        logger.debug("Prompt availability probe failed for '%s': %s", name, e)
        return None


def _reset_client() -> None:
    """Reset the prompt TTL caches (for testing)."""
    _missing_prompts_until.clear()
    _known_prompts_until.clear()
