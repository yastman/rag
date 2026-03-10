"""Tests for viewing appointment wizard dialog."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.dialogs.states import ViewingSG


def test_viewing_sg_has_date_state_only():
    assert hasattr(ViewingSG, "date")
    # phone/summary removed — phone_collector handles phone collection
    assert not hasattr(ViewingSG, "phone")
    assert not hasattr(ViewingSG, "summary")
    assert not hasattr(ViewingSG, "objects")


# --- Date options ---


@pytest.mark.asyncio
async def test_get_date_options_returns_5_items():
    from telegram_bot.dialogs.viewing import get_date_options

    result = await get_date_options()
    items = result["items"]
    assert len(items) == 5
    keys = [key for _, key in items]
    assert "nearest" in keys
    assert "next_week" in keys
    assert "next_month" in keys
    assert "unknown" in keys
    assert "phone" in keys


# --- Due date calculation ---


def test_compute_due_date_nearest():
    import time

    from telegram_bot.dialogs.viewing import compute_due_date

    now = int(time.time())
    due = compute_due_date("nearest")
    assert abs(due - now - 3 * 86400) < 5


def test_compute_due_date_unknown_defaults_7_days():
    import time

    from telegram_bot.dialogs.viewing import compute_due_date

    now = int(time.time())
    due = compute_due_date("unknown")
    assert abs(due - now - 7 * 86400) < 5


# --- Dialog structure ---


def test_viewing_dialog_exists():
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.viewing import viewing_dialog

    assert isinstance(viewing_dialog, Dialog)


def test_viewing_dialog_has_one_window():
    from telegram_bot.dialogs.viewing import viewing_dialog

    windows = viewing_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert ViewingSG.date in states
    assert len(windows) == 1


# --- Date handler → phone_collector ---


@pytest.mark.asyncio
async def test_on_date_selected_closes_dialog_and_starts_phone_collector():
    """After date selection, dialog should close and start phone_collector FSM."""
    from aiogram_dialog import ShowMode

    from telegram_bot.dialogs.viewing import on_date_selected

    state = AsyncMock()
    callback = MagicMock()
    callback.message = AsyncMock()
    callback.message.delete = AsyncMock()
    callback.answer = AsyncMock()
    callback.from_user = SimpleNamespace(id=123)

    manager = MagicMock()
    manager.middleware_data = {"state": state}
    manager.done = AsyncMock()

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_start:
        await on_date_selected(callback, SimpleNamespace(), manager, "next_week")

    # Dialog should be closed
    assert manager.show_mode == ShowMode.NO_UPDATE
    manager.done.assert_awaited_once()

    # date_range saved to FSM state
    state.update_data.assert_awaited_once_with(date_range="next_week")

    # phone_collector started with custom prompt
    mock_start.assert_awaited_once()
    call_kwargs = mock_start.await_args
    assert call_kwargs.args == (callback, state)
    assert call_kwargs.kwargs["service_key"] == "viewing"
    assert "осмотра" in call_kwargs.kwargs["prompt_text"]


@pytest.mark.asyncio
async def test_on_date_selected_deletes_inline_message():
    """Inline keyboard message should be deleted before phone_collector prompt."""
    from telegram_bot.dialogs.viewing import on_date_selected

    state = AsyncMock()
    msg = AsyncMock()
    callback = MagicMock()
    callback.message = msg
    callback.answer = AsyncMock()
    callback.from_user = SimpleNamespace(id=456)

    manager = MagicMock()
    manager.middleware_data = {"state": state}
    manager.done = AsyncMock()

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ):
        await on_date_selected(callback, SimpleNamespace(), manager, "nearest")

    msg.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_on_date_selected_no_state_logs_warning():
    """If FSMContext is not in middleware_data, should log warning and return."""
    from telegram_bot.dialogs.viewing import on_date_selected

    callback = MagicMock()
    callback.message = AsyncMock()
    callback.answer = AsyncMock()

    manager = MagicMock()
    manager.middleware_data = {}  # no "state"
    manager.done = AsyncMock()

    with patch(
        "telegram_bot.handlers.phone_collector.start_phone_collection", new_callable=AsyncMock
    ) as mock_start:
        await on_date_selected(callback, SimpleNamespace(), manager, "nearest")

    # phone_collector should NOT be started
    mock_start.assert_not_awaited()


# --- Cancel → HandoffSG ---


@pytest.mark.asyncio
async def test_cancel_starts_handoff_dialog():
    """Cancel button should start HandoffSG.goal dialog."""
    from aiogram_dialog import StartMode

    from telegram_bot.dialogs.states import HandoffSG
    from telegram_bot.dialogs.viewing import on_cancel_to_manager

    manager = AsyncMock()
    callback = MagicMock()

    await on_cancel_to_manager(callback, MagicMock(), manager)

    manager.start.assert_awaited_once_with(HandoffSG.goal, mode=StartMode.RESET_STACK)
