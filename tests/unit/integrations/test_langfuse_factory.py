"""Tests for Langfuse CallbackHandler factory."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch


class TestLangfuseFactory:
    def test_returns_none_when_disabled(self):
        from telegram_bot.integrations.langfuse import create_langfuse_handler

        with patch.dict(os.environ, {}, clear=True):
            result = create_langfuse_handler(session_id="s-1", user_id="123")
        assert result is None

    def test_returns_handler_when_enabled(self):
        from telegram_bot.integrations.langfuse import create_langfuse_handler

        env = {
            "LANGFUSE_SECRET_KEY": "sk-lf-test",
            "LANGFUSE_PUBLIC_KEY": "pk-lf-test",
            "LANGFUSE_HOST": "http://langfuse:3001",
        }
        mock_handler = MagicMock()
        mock_cls = MagicMock(return_value=mock_handler)
        with patch.dict(os.environ, env):
            with patch("langfuse.langchain.CallbackHandler", mock_cls):
                handler = create_langfuse_handler(session_id="s-1", user_id="123")
        assert handler is mock_handler
        mock_cls.assert_called_once_with(
            session_id="s-1",
            user_id="123",
            tags=["telegram", "rag", "langgraph"],
        )

    def test_custom_tags(self):
        from telegram_bot.integrations.langfuse import create_langfuse_handler

        env = {"LANGFUSE_SECRET_KEY": "sk-lf-test"}
        mock_cls = MagicMock(return_value=MagicMock())
        with patch.dict(os.environ, env):
            with patch("langfuse.langchain.CallbackHandler", mock_cls):
                create_langfuse_handler(session_id="s-1", user_id="1", tags=["custom"])
        mock_cls.assert_called_once_with(
            session_id="s-1",
            user_id="1",
            tags=["custom"],
        )

    def test_returns_none_on_exception(self):
        from telegram_bot.integrations.langfuse import create_langfuse_handler

        env = {"LANGFUSE_SECRET_KEY": "sk-lf-test"}
        with patch.dict(os.environ, env):
            with patch(
                "langfuse.langchain.CallbackHandler",
                side_effect=Exception("connection failed"),
            ):
                result = create_langfuse_handler(session_id="s-1", user_id="1")
        assert result is None
