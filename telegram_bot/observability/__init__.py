"""Observability package for telegram_bot (card_265772dd6bd4).

Consolidates previously scattered observability stubs:
- ``telegram_bot/observability.py``  → re-exports from src.observability
- ``telegram_bot/_bot_observability.py`` → _build_trace_metadata (now in .trace)
- ``telegram_bot/tracing_context.py`` → make_session_id, classify_action (now in .context)

All old import paths remain valid via backward-compat shims in the original modules.

Langfuse SDK removed (#2844, #2969) — create_callback_handler and traced_pipeline
are no-op shims kept for import compatibility.
"""

from src.observability import (
    get_client,
    mask_pii,
    observe,
    propagate_attributes,
    traced_pipeline,
)
from telegram_bot.observability.context import classify_action, make_session_id
from telegram_bot.observability.trace import _build_trace_metadata


def create_callback_handler(*_args: object, **_kwargs: object) -> None:
    """No-op shim — Langfuse callback handler removed (#2844, #2969)."""
    # ponytail: callers guard on None; returning None collapses every guarded path.
    return


__all__ = [
    "_build_trace_metadata",
    "classify_action",
    "create_callback_handler",
    "get_client",
    "make_session_id",
    "mask_pii",
    "observe",
    "propagate_attributes",
    "traced_pipeline",
]
