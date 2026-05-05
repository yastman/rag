"""Unit tests for telegram_formatting Langfuse output recording."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.services.telegram_formatting import (
    _record_langfuse_response_output,
    send_html_messages,
)


class TestRecordLangfuseResponseOutput:
    def test_no_op_when_client_is_none(self):
        with patch("telegram_bot.services.telegram_formatting.get_client", return_value=None):
            # Should not raise
            _record_langfuse_response_output("answer", 2)

    def test_uses_update_current_trace_when_present(self):
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()
        mock_lf.update_current_span = MagicMock()

        with patch("telegram_bot.services.telegram_formatting.get_client", return_value=mock_lf):
            _record_langfuse_response_output("hello world", 1)

        mock_lf.update_current_trace.assert_called_once_with(
            output={"response_preview": "hello world", "chunks_count": 1}
        )
        mock_lf.update_current_span.assert_not_called()

    def test_falls_back_to_update_current_span(self):
        mock_lf = MagicMock()
        del mock_lf.update_current_trace
        mock_lf.update_current_span = MagicMock()

        with patch("telegram_bot.services.telegram_formatting.get_client", return_value=mock_lf):
            _record_langfuse_response_output("fallback", 3)

        mock_lf.update_current_span.assert_called_once_with(
            output={"response_preview": "fallback", "chunks_count": 3}
        )

    def test_no_op_when_both_methods_missing(self):
        mock_lf = MagicMock()
        del mock_lf.update_current_trace
        del mock_lf.update_current_span

        with patch("telegram_bot.services.telegram_formatting.get_client", return_value=mock_lf):
            _record_langfuse_response_output("answer", 1)

    def test_trace_failure_falls_back_to_span(self):
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock(side_effect=RuntimeError("trace error"))
        mock_lf.update_current_span = MagicMock()

        with patch("telegram_bot.services.telegram_formatting.get_client", return_value=mock_lf):
            _record_langfuse_response_output("answer", 1)

        mock_lf.update_current_trace.assert_called_once()
        mock_lf.update_current_span.assert_called_once_with(
            output={"response_preview": "answer", "chunks_count": 1}
        )

    def test_span_failure_is_silent(self):
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock(side_effect=RuntimeError("trace error"))
        mock_lf.update_current_span = MagicMock(side_effect=RuntimeError("span error"))

        with patch("telegram_bot.services.telegram_formatting.get_client", return_value=mock_lf):
            # Should not raise
            _record_langfuse_response_output("answer", 1)

    def test_preview_truncated_to_800_chars(self):
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()

        long_text = "x" * 2000
        with patch("telegram_bot.services.telegram_formatting.get_client", return_value=mock_lf):
            _record_langfuse_response_output(long_text, 1)

        call_args = mock_lf.update_current_trace.call_args.kwargs
        assert len(call_args["output"]["response_preview"]) == 800
        assert call_args["output"]["chunks_count"] == 1

    def test_none_text_handled(self):
        mock_lf = MagicMock()
        mock_lf.update_current_trace = MagicMock()

        with patch("telegram_bot.services.telegram_formatting.get_client", return_value=mock_lf):
            _record_langfuse_response_output(None, 1)

        call_args = mock_lf.update_current_trace.call_args.kwargs
        assert call_args["output"]["response_preview"] == ""
        assert call_args["output"]["chunks_count"] == 1


class TestSendHtmlMessagesLangfuse:
    async def test_records_output_after_successful_send(self):
        message = MagicMock()
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.services.telegram_formatting._record_langfuse_response_output"
        ) as mock_record:
            result = await send_html_messages(message, "Hello")

        assert result is True
        mock_record.assert_called_once_with("Hello", 1)

    async def test_records_output_for_multi_chunk(self):
        message = MagicMock()
        message.answer = AsyncMock()
        long_text = "A" * 5000

        with patch(
            "telegram_bot.services.telegram_formatting._record_langfuse_response_output"
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
            "telegram_bot.services.telegram_formatting._record_langfuse_response_output"
        ) as mock_record:
            result = await send_html_messages(message, "")

        assert result is False
        mock_record.assert_not_called()

    async def test_langfuse_failure_does_not_break_sending(self):
        message = MagicMock()
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.services.telegram_formatting._record_langfuse_response_output",
            side_effect=RuntimeError("langfuse down"),
        ) as mock_record:
            # Should not raise
            result = await send_html_messages(message, "Hello")

        assert result is True
        mock_record.assert_called_once()
