"""Tests for Langfuse CallbackHandler factory (#413)."""

from __future__ import annotations


def test_create_callback_handler_is_importable():
    """create_callback_handler is part of the public API."""
    from telegram_bot.observability import create_callback_handler

    assert callable(create_callback_handler)


def test_create_callback_handler_returns_value():
    """create_callback_handler returns handler or None depending on LANGFUSE_ENABLED."""
    from telegram_bot.observability import LANGFUSE_ENABLED, create_callback_handler

    result = create_callback_handler()
    if LANGFUSE_ENABLED:
        assert result is not None
    else:
        assert result is None


def test_create_callback_handler_accepts_trace_context():
    """create_callback_handler accepts trace_context kwarg."""
    from telegram_bot.observability import LANGFUSE_ENABLED, create_callback_handler

    result = create_callback_handler(trace_context={"trace_id": "test-123"})
    if LANGFUSE_ENABLED:
        assert result is not None
    else:
        assert result is None
