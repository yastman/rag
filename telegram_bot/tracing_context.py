"""Backward-compat shim — moved to telegram_bot/observability/context.py (card_265772dd6bd4).

Callers using ``from telegram_bot.tracing_context import make_session_id``
continue to work without changes.
"""

from telegram_bot.observability.context import (
    classify_action as classify_action,
)
from telegram_bot.observability.context import (
    make_session_id as make_session_id,
)


__all__ = [
    "classify_action",
    "make_session_id",
]
