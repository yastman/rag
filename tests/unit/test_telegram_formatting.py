"""Unit tests for telegram_formatting helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from telegram_bot.services.generation.telegram_formatting import send_html_messages


class TestSendHtmlMessages:
    async def test_sends_and_returns_true(self):
        message = MagicMock()
        message.answer = AsyncMock()
        result = await send_html_messages(message, "Hello")
        assert result is True

    async def test_empty_text_returns_false(self):
        message = MagicMock()
        result = await send_html_messages(message, "")
        assert result is False
