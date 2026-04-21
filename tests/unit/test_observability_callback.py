"""Tests for Langfuse CallbackHandler factory (#413)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_create_callback_handler_is_importable():
    """create_callback_handler is part of the public API."""
    from telegram_bot.observability import create_callback_handler

    assert callable(create_callback_handler)


def test_create_callback_handler_returns_none_when_langfuse_uninitialized():
    """Without initialized Langfuse client, callback creation is skipped."""
    from telegram_bot.observability import create_callback_handler

    with patch("telegram_bot.observability.get_langfuse_client", return_value=None):
        assert create_callback_handler() is None


def test_create_callback_handler_builds_v4_handler():
    """When Langfuse client exists, factory returns v4 CallbackHandler instance."""
    from telegram_bot.observability import create_callback_handler

    fake_handler = object()
    with (
        patch("telegram_bot.observability.get_langfuse_client", return_value=MagicMock()),
        patch("langfuse.langchain.CallbackHandler", return_value=fake_handler) as mock_handler,
    ):
        result = create_callback_handler(trace_context={"session_id": "s1"})

    assert result is fake_handler
    mock_handler.assert_called_once_with(trace_context={"session_id": "s1"})


def test_observability_exports_native_v4_symbols():
    """Shared observability module re-exports native v4 entrypoints."""
    from telegram_bot import observability

    assert observability.propagate_attributes is not None
    assert observability.observe is not None
    assert observability.get_client is not None
