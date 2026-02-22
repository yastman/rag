"""Langfuse observability helpers with runtime initialization.

This module always exposes the real Langfuse SDK APIs (`observe`, `get_client`,
`propagate_attributes`) and relies on SDK-native graceful degradation when
credentials are unavailable.

Use `initialize_langfuse()` after loading runtime config (e.g. BotConfig) to
ensure credentials from `.env`/environment are applied before first tracing.
"""

import logging
import os
import re
from typing import Any

from langfuse import (
    Langfuse,
)
from langfuse import (
    get_client as _real_get_client,
)
from langfuse import (
    observe as _real_observe,
)
from langfuse import (
    propagate_attributes as _real_propagate,
)


logger = logging.getLogger(__name__)

_langfuse_client: Langfuse | None = None
_langfuse_init_attempted = False


# ---------------------------------------------------------------------------
# PII masking (always available)
# ---------------------------------------------------------------------------


def mask_pii(data: Any) -> Any:
    """Mask PII before sending to Langfuse.

    Applied to all inputs/outputs/metadata automatically.

    Masks:
    - Telegram user IDs (9-10 digits)
    - Phone numbers (10-15 digits with optional +)
    - Email addresses
    - Long texts (>500 chars truncated)
    """
    if isinstance(data, str):
        # Mask Telegram user IDs (9-10 digits not part of larger number)
        data = re.sub(r"\b\d{9,10}\b", "[USER_ID]", data)
        # Mask phone numbers
        data = re.sub(r"\+?\d{10,15}", "[PHONE]", data)
        # Mask emails
        data = re.sub(r"[\w.-]+@[\w.-]+\.\w+", "[EMAIL]", data)
        # Truncate long texts
        if len(data) > 500:
            data = data[:500] + "... [TRUNCATED]"
        return data
    if isinstance(data, dict):
        return {k: mask_pii(v) for k, v in data.items()}
    if isinstance(data, list):
        return [mask_pii(item) for item in data]
    return data


# ---------------------------------------------------------------------------
# Public SDK exports
# ---------------------------------------------------------------------------

observe = _real_observe
get_client = _real_get_client
propagate_attributes = _real_propagate


def _resolve_config_value(explicit: str | None, env_name: str) -> str | None:
    """Resolve explicit override first, then environment variable."""
    value = explicit if explicit is not None else os.getenv(env_name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def initialize_langfuse(
    *,
    public_key: str | None = None,
    secret_key: str | None = None,
    host: str | None = None,
    force: bool = False,
) -> Langfuse | None:
    """Initialize a Langfuse client after runtime config is loaded.

    Returns None when credentials are missing or client creation fails.
    """
    global _langfuse_client
    global _langfuse_init_attempted

    if _langfuse_client is not None and not force:
        return _langfuse_client

    resolved_public_key = _resolve_config_value(public_key, "LANGFUSE_PUBLIC_KEY")
    resolved_secret_key = _resolve_config_value(secret_key, "LANGFUSE_SECRET_KEY")
    resolved_host = _resolve_config_value(host, "LANGFUSE_HOST")

    if not resolved_public_key or not resolved_secret_key:
        _langfuse_client = None
        if force or not _langfuse_init_attempted:
            logger.info("Langfuse disabled (missing LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY)")
        _langfuse_init_attempted = True
        return None

    kwargs: dict[str, Any] = {
        "public_key": resolved_public_key,
        "secret_key": resolved_secret_key,
        "mask": mask_pii,  # type: ignore[arg-type]  # MaskFunction typing mismatch
        "flush_at": 50,
        "flush_interval": 5,
    }
    if resolved_host:
        kwargs["host"] = resolved_host

    try:
        _langfuse_client = Langfuse(**kwargs)
        _langfuse_init_attempted = True
        logger.info("Langfuse observability initialized")
        return _langfuse_client
    except Exception:
        logger.warning("Failed to initialize Langfuse client", exc_info=True)
        _langfuse_client = None
        _langfuse_init_attempted = True
        return None


def get_langfuse_client() -> Langfuse | None:
    """Get initialized Langfuse client, lazy-initializing from env when possible."""
    if _langfuse_client is not None:
        return _langfuse_client
    return initialize_langfuse()


def create_callback_handler(
    *,
    trace_context: Any | None = None,
    update_trace: bool = False,
):
    """Create Langfuse CallbackHandler for create_agent integration.

    Returns None when Langfuse is not configured or handler init fails.
    """
    if get_langfuse_client() is None:
        return None

    try:
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(
            trace_context=trace_context,
            update_trace=update_trace,
        )
    except Exception:
        logger.warning("Failed to create Langfuse CallbackHandler", exc_info=True)
        return None


def traced_pipeline(
    *,
    session_id: str,
    user_id: str,
    tags: list[str] | None = None,
):
    """Context manager for pipeline-level trace propagation.

    Wraps propagate_attributes with sensible defaults.
    Use at any entry point that invokes @observe-decorated functions.
    """
    return propagate_attributes(
        session_id=session_id,
        user_id=user_id,
        tags=tags or [],
    )


def _reset_langfuse_client_for_tests() -> None:
    """Reset module-level client cache (test-only helper)."""
    global _langfuse_client
    global _langfuse_init_attempted
    _langfuse_client = None
    _langfuse_init_attempted = False
