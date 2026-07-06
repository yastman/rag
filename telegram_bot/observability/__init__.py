"""Observability package for telegram_bot (card_265772dd6bd4).

Consolidates previously scattered observability stubs:
- ``telegram_bot/observability.py``  → re-exports from src.observability
- ``telegram_bot/_bot_observability.py`` → _build_trace_metadata (now in .trace)
- ``telegram_bot/tracing_context.py`` → make_session_id, classify_action (now in .context)

All old import paths remain valid via backward-compat shims in the original modules.

No-op shims removed (card_9967cd60fe32):
  create_callback_handler, get_client, observe, propagate_attributes,
  traced_pipeline — confirmed 0 prod callers.
"""

from src.observability import mask_pii
from telegram_bot.observability.context import classify_action, make_session_id
from telegram_bot.observability.trace import _build_trace_metadata


__all__ = [
    "_build_trace_metadata",
    "classify_action",
    "make_session_id",
    "mask_pii",
]
