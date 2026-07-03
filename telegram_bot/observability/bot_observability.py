"""Backward-compat shim — moved to telegram_bot/observability/trace.py (card_265772dd6bd4).

``telegram_bot._bot_observability`` is pinned by the contract test
``tests/contract/test_bot_observability_extraction_contract.py``.
This shim keeps that path intact while the canonical implementation
now lives in :mod:`telegram_bot.observability.trace`.

The module avoids ``aiogram`` / ``langgraph`` / ``fastapi`` imports so it
stays cheap to import and easy to unit-test in isolation.
"""

from telegram_bot.observability.trace import (
    _build_trace_metadata as _build_trace_metadata,
)


__all__ = [
    "_build_trace_metadata",
]
