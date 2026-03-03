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
        cache_ttl: Cache TTL in seconds (default 300).
        variables: Variables for prompt.compile() (e.g. {"domain": "недвижимость"}).

    Returns:
        Compiled prompt string from Langfuse, or the fallback.
    """
    vars_ = variables or {}
    lf = get_client()
    lf.update_current_span(
        input={
            "prompt_name": name,
            "cache_ttl_s": cache_ttl,
            "has_variables": bool(vars_),
            "variables_count": len(vars_),
        }
    )

    def _finish(value: str, *, source: str, reason: str, prompt_version: int | None = None) -> str:
        output: dict[str, Any] = {"source": source, "reason": reason, "result_length": len(value)}
        if prompt_version is not None:
            output["prompt_version"] = prompt_version
        lf.update_current_span(output=output)
        return value

    client = get_client()
    if client is None:
        return _finish(
            _apply_fallback_vars(fallback, vars_),
            source="fallback",
            reason="client_unavailable",
        )

    if _is_temporarily_missing(name):
        return _finish(
            _apply_fallback_vars(fallback, vars_),
            source="fallback",
            reason="missing_cache_ttl",
        )

    if not _is_temporarily_known(name):
        available = _probe_prompt_available(client, name)
        if available is False:
            _missing_prompts_until[name] = time.monotonic() + cache_ttl
            logger.debug(
                "Prompt '%s' not found in Langfuse API, using fallback for %ds",
                name,
                cache_ttl,
            )
            return _finish(
                _apply_fallback_vars(fallback, vars_),
                source="fallback",
                reason="probe_not_found",
            )
        if available is True:
            _known_prompts_until[name] = time.monotonic() + cache_ttl

    try:
        # Do not pass fallback to SDK: for missing prompts SDK logs noisy warnings on each call.
        # We handle fallback ourselves and cache "not found" locally.
        prompt = client.get_prompt(name, cache_ttl_seconds=cache_ttl)
        _missing_prompts_until.pop(name, None)
        version: int | None = getattr(prompt, "version", None)
        if vars_:
            return _finish(
                str(prompt.compile(**vars_)),
                source="langfuse",
                reason="compiled_with_variables",
                prompt_version=version,
            )
        return _finish(
            str(prompt.compile()), source="langfuse", reason="compiled", prompt_version=version
        )
    except Exception as e:
        if _is_prompt_not_found(e):
            # Avoid hitting Langfuse on every request when prompt/label is absent.
            _missing_prompts_until[name] = time.monotonic() + cache_ttl
            logger.debug(
                "Prompt '%s' not found in Langfuse, using fallback for %ds",
                name,
                cache_ttl,
            )
            return _finish(
                _apply_fallback_vars(fallback, vars_),
                source="fallback",
                reason="prompt_not_found",
            )

        logger.warning("Failed to fetch prompt '%s', using fallback", name, exc_info=True)
        return _finish(
            _apply_fallback_vars(fallback, vars_),
            source="fallback",
            reason="fetch_error",
        )


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
    """Reset the prompt TTL caches (for testing)."""
    _missing_prompts_until.clear()
    _known_prompts_until.clear()
