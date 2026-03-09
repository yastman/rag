"""Tests for Langfuse error reporting in error handler."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.middlewares.error_handler import handle_error


def _make_error_event(exception: Exception) -> MagicMock:
    event = MagicMock()
    event.exception = exception
    event.update.message = MagicMock()
    event.update.message.answer = AsyncMock()
    event.update.callback_query = None
    return event


async def test_reports_error_to_langfuse():
    """handle_error calls update_current_observation with ERROR level."""
    mock_lf = MagicMock()
    mock_lf.get_current_trace_id.return_value = "trace-123"

    event = _make_error_event(ValueError("test error"))

    with patch(
        "telegram_bot.middlewares.error_handler.get_client",
        return_value=mock_lf,
        create=True,
    ):
        # Patch the import inside handle_error
        with patch.dict(
            "sys.modules",
            {"telegram_bot.observability": MagicMock(get_client=MagicMock(return_value=mock_lf))},
        ):
            await handle_error(event)

    mock_lf.update_current_observation.assert_called_once()
    call_kwargs = mock_lf.update_current_observation.call_args[1]
    assert call_kwargs["level"] == "ERROR"
    assert "ValueError" in call_kwargs["status_message"]


async def test_no_langfuse_report_when_no_trace():
    """When no active trace, skip langfuse reporting gracefully."""
    mock_lf = MagicMock()
    mock_lf.get_current_trace_id.return_value = None

    event = _make_error_event(RuntimeError("oops"))

    with patch.dict(
        "sys.modules",
        {"telegram_bot.observability": MagicMock(get_client=MagicMock(return_value=mock_lf))},
    ):
        await handle_error(event)

    mock_lf.update_current_observation.assert_not_called()


async def test_langfuse_report_failure_is_swallowed():
    """If Langfuse reporting itself fails, error handler still works."""
    event = _make_error_event(TypeError("bad type"))

    with patch.dict(
        "sys.modules",
        {
            "telegram_bot.observability": MagicMock(
                get_client=MagicMock(side_effect=ImportError("no langfuse"))
            )
        },
    ):
        await handle_error(event)

    event.update.message.answer.assert_awaited_once()
