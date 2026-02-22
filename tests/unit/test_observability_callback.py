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


def test_create_callback_handler_builds_handler_when_client_available():
    """When Langfuse client exists, factory returns CallbackHandler instance."""
    from telegram_bot.observability import create_callback_handler

    fake_handler = object()
    with (
        patch("telegram_bot.observability.get_langfuse_client", return_value=MagicMock()),
        patch("langfuse.langchain.CallbackHandler", return_value=fake_handler) as mock_handler,
    ):
        result = create_callback_handler(
            trace_context={"trace_id": "test-123"},
            update_trace=True,
        )

    assert result is fake_handler
    mock_handler.assert_called_once_with(
        trace_context={"trace_id": "test-123"},
        update_trace=True,
    )
