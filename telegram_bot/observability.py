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

    def create_score(self, **kwargs: Any) -> None:
        pass

    def get_current_trace_id(self) -> str:
        return ""

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
            mask=mask_pii,  # type: ignore[arg-type]  # MaskFunction stub mismatch
            flush_at=50,
            flush_interval=5,
        )

    def create_callback_handler(
        *,
        trace_context: Any | None = None,
        update_trace: bool = False,
    ):
        """Create a Langfuse CallbackHandler for create_agent integration.

        Returns a NEW handler per invocation. Use inside propagate_attributes()
        context to inherit session_id, user_id, tags automatically (SDK v3).
        """
        from langfuse.langchain import CallbackHandler

        return CallbackHandler(
            trace_context=trace_context,
            update_trace=update_trace,
        )

    logger.info("Langfuse observability ENABLED")
else:
    from contextlib import contextmanager

    observe = _noop_observe  # type: ignore[assignment]  # noop stub for disabled Langfuse
    get_client = _noop_get_client  # type: ignore[assignment]  # noop stub for disabled Langfuse

    @contextmanager
    def _noop_propagate(**kwargs: Any):
        yield

    propagate_attributes = _noop_propagate  # type: ignore[assignment]  # noop stub

    def get_langfuse_client() -> None:  # type: ignore[misc]  # conditional return type
        """Langfuse disabled — return None."""
        return

    def create_callback_handler(**kwargs: Any):  # type: ignore[misc]  # noop stub
        """Noop when Langfuse disabled."""
        return

    logger.info("Langfuse observability DISABLED (LANGFUSE_SECRET_KEY not set)")


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
