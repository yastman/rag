"""Tests for LangfuseContextMiddleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.middlewares.langfuse_middleware import LangfuseContextMiddleware


@pytest.fixture
def middleware():
    return LangfuseContextMiddleware()


@pytest.fixture
def handler():
    return AsyncMock(return_value="ok")


@pytest.fixture
def message_event():
    from aiogram.types import Message

    msg = MagicMock(spec=Message)
    msg.text = "/start"
    return msg


@pytest.fixture
def event_data():
    user = MagicMock()
    user.id = 42
    chat = MagicMock()
    chat.id = 100
    return {"event_from_user": user, "event_chat": chat}


async def test_passthrough_when_langfuse_disabled(middleware, handler, message_event, event_data):
    """When get_client() returns None, handler is called directly."""
    with patch("telegram_bot.middlewares.langfuse_middleware.get_client", return_value=None):
        result = await middleware(handler, message_event, event_data)

    assert result == "ok"
    handler.assert_awaited_once_with(message_event, event_data)


async def test_creates_span_when_langfuse_enabled(middleware, handler, message_event, event_data):
    """When Langfuse is available, wraps handler in span + propagate_attributes."""
    mock_lf = MagicMock()
    mock_span_ctx = MagicMock()
    mock_span_ctx.__enter__ = MagicMock(return_value=mock_span_ctx)
    mock_span_ctx.__exit__ = MagicMock(return_value=False)
    mock_lf.start_as_current_span.return_value = mock_span_ctx

    mock_prop_ctx = MagicMock()
    mock_prop_ctx.__enter__ = MagicMock(return_value=mock_prop_ctx)
    mock_prop_ctx.__exit__ = MagicMock(return_value=False)

    with (
        patch("telegram_bot.middlewares.langfuse_middleware.get_client", return_value=mock_lf),
        patch(
            "telegram_bot.middlewares.langfuse_middleware.propagate_attributes",
            return_value=mock_prop_ctx,
        ) as mock_propagate,
    ):
        result = await middleware(handler, message_event, event_data)

    assert result == "ok"
    handler.assert_awaited_once()
    mock_lf.start_as_current_span.assert_called_once_with(name="telegram-cmd-start")
    mock_propagate.assert_called_once()
    call_kwargs = mock_propagate.call_args[1]
    assert call_kwargs["user_id"] == "42"
    assert "telegram" in call_kwargs["tags"]


async def test_handles_missing_user(middleware, handler, message_event):
    """When event_from_user is missing, user_id is None."""
    data: dict = {}
    with patch("telegram_bot.middlewares.langfuse_middleware.get_client", return_value=None):
        result = await middleware(handler, message_event, data)

    assert result == "ok"


async def test_callback_action_type(middleware, handler, event_data):
    """CallbackQuery events get classified as callback-{prefix}."""
    from aiogram.types import CallbackQuery

    cb = MagicMock(spec=CallbackQuery)
    cb.data = "fav:add:123"

    mock_lf = MagicMock()
    mock_span_ctx = MagicMock()
    mock_span_ctx.__enter__ = MagicMock(return_value=mock_span_ctx)
    mock_span_ctx.__exit__ = MagicMock(return_value=False)
    mock_lf.start_as_current_span.return_value = mock_span_ctx

    mock_prop_ctx = MagicMock()
    mock_prop_ctx.__enter__ = MagicMock(return_value=mock_prop_ctx)
    mock_prop_ctx.__exit__ = MagicMock(return_value=False)

    with (
        patch("telegram_bot.middlewares.langfuse_middleware.get_client", return_value=mock_lf),
        patch(
            "telegram_bot.middlewares.langfuse_middleware.propagate_attributes",
            return_value=mock_prop_ctx,
        ),
    ):
        await middleware(handler, cb, event_data)

    mock_lf.start_as_current_span.assert_called_once_with(name="telegram-callback-fav")
