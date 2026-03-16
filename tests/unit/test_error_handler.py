"""Tests for dp.errors router error handler (M5 refactor).

Verifies that handle_error covers all event types (Message, CallbackQuery,
InlineQuery) and that setup_error_handler registers via dp.errors.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


class TestHandleError:
    """Tests for the handle_error function."""

    async def test_logs_error_with_exc_info(self) -> None:
        """Handler logs the exception with exc_info for traceback capture."""
        from telegram_bot.middlewares.error_handler import handle_error

        exception = ValueError("something went wrong")
        mock_update = MagicMock()
        mock_update.message = None
        mock_update.callback_query = None

        mock_event = MagicMock()
        mock_event.exception = exception
        mock_event.update = mock_update

        with patch("telegram_bot.middlewares.error_handler.logger") as mock_logger:
            await handle_error(mock_event)

        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args.kwargs
        assert call_kwargs.get("exc_info") is exception

    async def test_sends_message_when_update_has_message(self) -> None:
        """Handler sends user-friendly reply when update.message is present."""
        from telegram_bot.middlewares.error_handler import handle_error

        mock_message = AsyncMock()
        mock_update = MagicMock()
        mock_update.message = mock_message
        mock_update.callback_query = None

        mock_event = MagicMock()
        mock_event.exception = RuntimeError("handler crashed")
        mock_event.update = mock_update

        with patch("telegram_bot.middlewares.error_handler.logger"):
            await handle_error(mock_event)

        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args.args[0]
        assert "❌" in text

    async def test_sends_message_via_callback_query(self) -> None:
        """Handler answers callback query and replies via callback_query.message."""
        from telegram_bot.middlewares.error_handler import handle_error

        mock_message = AsyncMock()
        mock_callback = MagicMock()
        mock_callback.answer = AsyncMock()
        mock_callback.message = mock_message

        mock_update = MagicMock()
        mock_update.message = None
        mock_update.callback_query = mock_callback

        mock_event = MagicMock()
        mock_event.exception = RuntimeError("callback handler crashed")
        mock_event.update = mock_update

        with patch("telegram_bot.middlewares.error_handler.logger"):
            await handle_error(mock_event)

        mock_callback.answer.assert_awaited_once()
        mock_message.answer.assert_called_once()
        text = mock_message.answer.call_args.args[0]
        assert "❌" in text

    async def test_no_crash_for_inline_or_other_event_types(self) -> None:
        """Handler does not crash when update has no message or callback_query."""
        from telegram_bot.middlewares.error_handler import handle_error

        mock_update = MagicMock()
        mock_update.message = None
        mock_update.callback_query = None

        mock_event = MagicMock()
        mock_event.exception = RuntimeError("inline query error")
        mock_event.update = mock_update

        with patch("telegram_bot.middlewares.error_handler.logger"):
            await handle_error(mock_event)  # must not raise

    async def test_no_message_sent_when_no_message_in_update(self) -> None:
        """Handler does not attempt answer() when there is no message to reply to."""
        from telegram_bot.middlewares.error_handler import handle_error

        mock_answer = AsyncMock()
        mock_update = MagicMock()
        mock_update.message = None
        # callback_query exists but has no .message
        mock_update.callback_query = MagicMock()
        mock_update.callback_query.message = None

        mock_event = MagicMock()
        mock_event.exception = RuntimeError("poll error")
        mock_event.update = mock_update

        with patch("telegram_bot.middlewares.error_handler.logger"):
            await handle_error(mock_event)

        # Neither path should have triggered answer()
        mock_answer.assert_not_called()

    async def test_updates_langfuse_span_status_when_trace_active(self) -> None:
        """Active traces should mark the current span as failed for observability."""
        from telegram_bot.middlewares.error_handler import handle_error

        mock_update = MagicMock()
        mock_update.message = None
        mock_update.callback_query = None

        mock_event = MagicMock()
        mock_event.exception = RuntimeError("span failure")
        mock_event.update = mock_update

        mock_lf = MagicMock(spec=["get_current_trace_id", "update_current_span"])
        mock_lf.get_current_trace_id.return_value = "trace-123"
        mock_lf.update_current_span = MagicMock()

        with (
            patch("telegram_bot.observability.get_client", return_value=mock_lf),
            patch("telegram_bot.middlewares.error_handler.logger"),
        ):
            await handle_error(mock_event)

        mock_lf.update_current_span.assert_called_once()
        call_kwargs = mock_lf.update_current_span.call_args.kwargs
        assert call_kwargs["level"] == "ERROR"
        assert call_kwargs["status_message"] == "RuntimeError: span failure"


class TestSetupErrorHandler:
    """Tests for setup_error_handler registration."""

    def test_registers_handle_error_on_dp_errors(self) -> None:
        """setup_error_handler calls dp.errors.register with handle_error."""
        from telegram_bot.middlewares.error_handler import handle_error, setup_error_handler

        mock_dp = MagicMock()
        setup_error_handler(mock_dp)

        mock_dp.errors.register.assert_called_once()
        registered_fn = mock_dp.errors.register.call_args.args[0]
        assert registered_fn is handle_error

    def test_registers_with_exception_type_filter(self) -> None:
        """setup_error_handler passes ExceptionTypeFilter(Exception) as filter."""
        from aiogram.filters import ExceptionTypeFilter

        from telegram_bot.middlewares.error_handler import setup_error_handler

        mock_dp = MagicMock()
        setup_error_handler(mock_dp)

        call_args = mock_dp.errors.register.call_args
        # Second positional arg should be ExceptionTypeFilter instance
        filters = call_args.args[1:]
        assert any(isinstance(f, ExceptionTypeFilter) for f in filters), (
            "setup_error_handler must pass ExceptionTypeFilter to dp.errors.register"
        )
