"""Local prompt management — versioned templates only.

Replaces the former Langfuse-backed prompt manager (#2628).
All prompt text is owned locally; no runtime calls to external prompt stores.
"""

from __future__ import annotations

from typing import Any


def get_prompt(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = 3600,
    variables: dict[str, str] | None = None,
) -> str:
    """Return the local prompt template with optional variable substitution.

    Args:
        name: Prompt name (kept for call-site compatibility; not used for lookup).
        fallback: Local prompt template string (the only source of truth).
        cache_ttl: Accepted for call-site compatibility; ignored.
        variables: ``{{var}}`` substitutions applied to *fallback*.

    Returns:
        Compiled prompt string.
    """
    return _apply_fallback_vars(fallback, variables or {})


def get_prompt_with_config(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = 3600,
    variables: dict[str, str] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Return ``(compiled_prompt_text, config_dict)``.

    Config is always empty — model/temperature config lives in local settings,
    not in prompt payloads.
    """
    return _apply_fallback_vars(fallback, variables or {}), {}


def get_prompt_with_object(
    name: str,
    *,
    fallback: str,
    cache_ttl: int = 3600,
    variables: dict[str, str] | None = None,
) -> tuple[str, None]:
    """Return ``(compiled_prompt_string, None)``.

    The second element is always ``None`` — there is no external prompt object.
    Call-sites that guard with ``if prompt_obj is not None`` will safely skip
    any Langfuse-specific linkage path.
    """
    return _apply_fallback_vars(fallback, variables or {}), None


def _apply_fallback_vars(fallback: str, compile_vars: dict[str, str]) -> str:
    """Apply ``{{var}}`` substitution on a prompt string."""
    if not compile_vars:
        return fallback
    result = fallback
    for key, value in compile_vars.items():
        result = result.replace("{{" + key + "}}", value)
    return result


def _reset_client() -> None:
    """No-op — kept for call-site compatibility (no caches to reset)."""
