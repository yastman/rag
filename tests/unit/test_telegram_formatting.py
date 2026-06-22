"""Unit tests for telegram_formatting output recording."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.services.telegram_formatting import (
    record_langfuse_response_output,
    send_html_messages,
)


class TestRecordLangfuseResponseOutput:
    """record_langfuse_response_output is a no-op stub (Langfuse removed in #2844)."""

    def test_no_op_does_not_raise(self):
        # Should not raise regardless of arguments
        record_langfuse_response_output("answer", 2)
        record_langfuse_response_output(None, 0)

    def test_private_output_helper_alias_points_to_public_helper(self):
        from telegram_bot.services import telegram_formatting

        assert (
            telegram_formatting._record_langfuse_response_output
            is telegram_formatting.record_langfuse_response_output
        )


class TestSendHtmlMessagesLangfuse:
    async def test_records_output_after_successful_send(self):
        message = MagicMock()
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.services.telegram_formatting.record_langfuse_response_output"
        ) as mock_record:
            result = await send_html_messages(message, "Hello")

        assert result is True
        mock_record.assert_called_once_with("Hello", 1)

    async def test_records_output_for_multi_chunk(self):
        message = MagicMock()
        message.answer = AsyncMock()
        long_text = "A" * 5000

        with patch(
            "telegram_bot.services.telegram_formatting.record_langfuse_response_output"
        ) as mock_record:
            result = await send_html_messages(message, long_text)

        assert result is True
        # Should be called with the number of chunks > 1
        call_args = mock_record.call_args
        assert call_args[0][0] == long_text
        assert call_args[0][1] > 1

    async def test_no_record_when_no_messages(self):
        message = MagicMock()

        with patch(
            "telegram_bot.services.telegram_formatting.record_langfuse_response_output"
        ) as mock_record:
            result = await send_html_messages(message, "")

        assert result is False
        mock_record.assert_not_called()

    async def test_langfuse_failure_does_not_break_sending(self):
        message = MagicMock()
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.services.telegram_formatting.record_langfuse_response_output",
            side_effect=RuntimeError("langfuse down"),
        ) as mock_record:
            # Should not raise
            result = await send_html_messages(message, "Hello")

        assert result is True
        mock_record.assert_called_once()
