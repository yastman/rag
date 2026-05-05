"""Unit tests for LangfuseContextMiddleware input extraction and root trace setup."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.middlewares.langfuse_middleware import (
    LangfuseContextMiddleware,
    _extract_event_input,
)


pytest.importorskip("aiogram", reason="aiogram not installed")

from aiogram.types import CallbackQuery, Message


class TestExtractEventInput:
    def test_message_text(self):
        msg = MagicMock(spec=Message)
        msg.text = "Hello world"
        msg.caption = None
        msg.content_type = "text"
        result = _extract_event_input(msg, "message")
        assert result == {
            "action": "message",
            "content_type": "text",
            "text_preview": "Hello world",
        }

    def test_message_caption_fallback(self):
        msg = MagicMock(spec=Message)
        msg.text = None
        msg.caption = "Photo caption"
        msg.content_type = "photo"
        result = _extract_event_input(msg, "message")
        assert result == {
            "action": "message",
            "content_type": "photo",
            "text_preview": "Photo caption",
        }

    def test_message_empty_text(self):
        msg = MagicMock(spec=Message)
        msg.text = None
        msg.caption = None
        msg.content_type = "contact"
        result = _extract_event_input(msg, "message")
        assert result == {
            "action": "message",
            "content_type": "contact",
            "text_preview": "",
        }

    def test_message_text_truncated(self):
        msg = MagicMock(spec=Message)
        msg.text = "x" * 1000
        msg.caption = None
        msg.content_type = "text"
        result = _extract_event_input(msg, "cmd-start")
        assert result["text_preview"] == "x" * 500
        assert result["action"] == "cmd-start"

    def test_callback_query(self):
        cb = MagicMock(spec=CallbackQuery)
        cb.data = "menu:search"
        result = _extract_event_input(cb, "callback-menu")
        assert result == {
            "action": "callback-menu",
            "callback_data": "menu:search",
        }

    def test_callback_query_long_data(self):
        cb = MagicMock(spec=CallbackQuery)
        cb.data = "x" * 300
        result = _extract_event_input(cb, "callback")
        assert result["callback_data"] == "x" * 200

    def test_unknown_event(self):
        event = MagicMock()
        result = _extract_event_input(event, "update")
        assert result == {"action": "update"}


class TestLangfuseContextMiddleware:
    @pytest.fixture
    def middleware(self) -> LangfuseContextMiddleware:
        return LangfuseContextMiddleware()

    async def test_no_langfuse_client_passes_through(self, middleware: LangfuseContextMiddleware):
        handler = AsyncMock(return_value="result")
        event = MagicMock(spec=Message)
        data = {"event_from_user": MagicMock(id=123), "event_chat": MagicMock(id=456)}

        with patch("telegram_bot.middlewares.langfuse_middleware.get_client", return_value=None):
            result = await middleware(handler, event, data)

        assert result == "result"
        handler.assert_called_once_with(event, data)

    async def test_root_observation_started_with_input(self, middleware: LangfuseContextMiddleware):
        handler = AsyncMock(return_value="handler_result")
        msg = MagicMock(spec=Message)
        msg.text = "user query"
        msg.caption = None
        msg.content_type = "text"
        data = {"event_from_user": MagicMock(id=123), "event_chat": MagicMock(id=456)}

        mock_lf = MagicMock()
        mock_obs_ctx = MagicMock()
        mock_lf.start_as_current_observation.return_value = mock_obs_ctx

        with (
            patch(
                "telegram_bot.middlewares.langfuse_middleware.get_client",
                return_value=mock_lf,
            ),
            patch("telegram_bot.middlewares.langfuse_middleware.propagate_attributes") as mock_prop,
        ):
            result = await middleware(handler, msg, data)

        assert result == "handler_result"
        mock_lf.start_as_current_observation.assert_called_once()
        call_kwargs = mock_lf.start_as_current_observation.call_args.kwargs
        assert call_kwargs["as_type"] == "span"
        assert call_kwargs["name"] == "telegram-message"
        assert call_kwargs["input"] == {
            "action": "message",
            "content_type": "text",
            "text_preview": "user query",
        }
        mock_prop.assert_called_once()
        handler.assert_called_once_with(msg, data)

    async def test_callback_observation_started_with_input(
        self, middleware: LangfuseContextMiddleware
    ):
        handler = AsyncMock(return_value="handler_result")
        cb = MagicMock(spec=CallbackQuery)
        cb.data = "filter:apply"
        data = {"event_from_user": MagicMock(id=789), "event_chat": None}

        mock_lf = MagicMock()
        mock_obs_ctx = MagicMock()
        mock_lf.start_as_current_observation.return_value = mock_obs_ctx

        with (
            patch(
                "telegram_bot.middlewares.langfuse_middleware.get_client",
                return_value=mock_lf,
            ),
            patch("telegram_bot.middlewares.langfuse_middleware.propagate_attributes") as mock_prop,
        ):
            result = await middleware(handler, cb, data)

        assert result == "handler_result"
        call_kwargs = mock_lf.start_as_current_observation.call_args.kwargs
        assert call_kwargs["name"] == "telegram-callback-filter"
        assert call_kwargs["input"] == {
            "action": "callback-filter",
            "callback_data": "filter:apply",
        }
        mock_prop.assert_called_once()

    async def test_uses_user_id_when_chat_missing(self, middleware: LangfuseContextMiddleware):
        handler = AsyncMock(return_value="result")
        event = MagicMock(spec=Message)
        event.text = None
        event.caption = None
        event.content_type = "text"
        user = MagicMock(id=42)
        data = {"event_from_user": user, "event_chat": None}

        mock_lf = MagicMock()
        mock_obs_ctx = MagicMock()
        mock_lf.start_as_current_observation.return_value = mock_obs_ctx

        with (
            patch(
                "telegram_bot.middlewares.langfuse_middleware.get_client",
                return_value=mock_lf,
            ),
            patch("telegram_bot.middlewares.langfuse_middleware.propagate_attributes") as mock_prop,
            patch(
                "telegram_bot.middlewares.langfuse_middleware.make_session_id",
                return_value="session-123",
            ) as mock_make_session,
        ):
            await middleware(handler, event, data)

        mock_make_session.assert_called_once_with("chat", 42)
        mock_prop.assert_called_once_with(
            session_id="session-123",
            user_id="42",
            tags=["telegram", "message"],
        )
