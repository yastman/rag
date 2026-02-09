# telegram_bot/observability.py
"""Langfuse observability with PII masking and graceful disable.

When LANGFUSE_SECRET_KEY is not set, all Langfuse functionality is disabled:
- @observe decorators become no-ops (zero overhead)
- get_client() returns a stub that silently ignores all calls
- get_langfuse_client() returns None

Set LANGFUSE_SECRET_KEY and LANGFUSE_PUBLIC_KEY to enable tracing.
"""

import logging
import os
import re
from typing import Any


logger = logging.getLogger(__name__)

LANGFUSE_ENABLED = bool(os.getenv("LANGFUSE_SECRET_KEY"))


# ---------------------------------------------------------------------------
# PII masking (always available, used when Langfuse IS enabled)
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
# No-op stubs (used when Langfuse is disabled)
# ---------------------------------------------------------------------------


class _NullLangfuseClient:
    """Stub that silently ignores all Langfuse client method calls."""

    def update_current_trace(self, **kwargs: Any) -> None:
        pass

    def update_current_span(self, **kwargs: Any) -> None:
        pass

    def update_current_generation(self, **kwargs: Any) -> None:
        pass

    def score_current_trace(self, **kwargs: Any) -> None:
        pass

    def flush(self) -> None:
        pass


_null_client = _NullLangfuseClient()


def _noop_observe(**kwargs: Any):
    """No-op @observe decorator — returns the function unchanged."""

    def decorator(func):
        return func

    return decorator


def _noop_get_client() -> _NullLangfuseClient:
    """Return the null client stub."""
    return _null_client


# ---------------------------------------------------------------------------
# Public API — conditional on LANGFUSE_ENABLED
# ---------------------------------------------------------------------------

if LANGFUSE_ENABLED:
    from langfuse import Langfuse
    from langfuse import get_client as _real_get_client
    from langfuse import observe as _real_observe
    from langfuse import propagate_attributes as _real_propagate

    observe = _real_observe
    get_client = _real_get_client
    propagate_attributes = _real_propagate

    def get_langfuse_client() -> Langfuse:
        """Get Langfuse client with PII masking enabled."""
        return Langfuse(
            mask=mask_pii,
            flush_at=50,
            flush_interval=5,
        )

    logger.info("Langfuse observability ENABLED")
else:
    from contextlib import contextmanager

    observe = _noop_observe
    get_client = _noop_get_client

    @contextmanager
    def _noop_propagate(**kwargs: Any):
        yield

    propagate_attributes = _noop_propagate

    def get_langfuse_client() -> None:  # type: ignore[return]
        """Langfuse disabled — return None."""
        return

    logger.info("Langfuse observability DISABLED (LANGFUSE_SECRET_KEY not set)")
