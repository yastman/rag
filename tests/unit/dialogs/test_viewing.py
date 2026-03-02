"""Tests for viewing appointment wizard dialog."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.states import ViewingSG


def test_viewing_sg_has_all_states():
    assert hasattr(ViewingSG, "objects")
    assert hasattr(ViewingSG, "objects_text")
    assert hasattr(ViewingSG, "date")
    assert hasattr(ViewingSG, "phone")
    assert hasattr(ViewingSG, "summary")


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


# --- Date handler ---


@pytest.mark.asyncio
async def test_on_date_selected_saves_and_switches_to_phone():
    from telegram_bot.dialogs.viewing import on_date_selected

    callback = MagicMock()
    callback.message = AsyncMock()
    callback.message.answer = AsyncMock()
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await on_date_selected(callback, SimpleNamespace(), manager, "next_week")
    assert manager.dialog_data["date_range"] == "next_week"
    manager.switch_to.assert_awaited_once_with(ViewingSG.phone)


# --- Objects getter (empty favorites) ---


@pytest.mark.asyncio
async def test_get_objects_options_empty_favorites():
    from telegram_bot.dialogs.viewing import get_objects_options

    result = await get_objects_options(
        event_from_user=SimpleNamespace(id=12345),
        favorites_service=None,
    )
    items = result["items"]
    assert len(items) == 0
    assert result["has_favorites"] is False


# --- Objects skip handler ---


@pytest.mark.asyncio
async def test_on_objects_skip_switches_to_date():
    from telegram_bot.dialogs.viewing import on_objects_skip

    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await on_objects_skip(MagicMock(), MagicMock(), manager)
    manager.switch_to.assert_awaited_once_with(ViewingSG.date)


# --- Summary getter ---


@pytest.mark.asyncio
async def test_get_summary_data_formats_all_fields():
    from telegram_bot.dialogs.viewing import get_summary_data

    manager = SimpleNamespace(
        dialog_data={
            "selected_objects": [{"complex_name": "Sunset", "property_type": "1+1"}],
            "date_range": "nearest",
            "phone": "+380990091392",
        }
    )
    result = await get_summary_data(dialog_manager=manager)
    assert "+380990091392" in result["summary_text"]
    assert "Sunset" in result["summary_text"]
    assert "Ближайшие дни" in result["summary_text"]


# --- Due date calculation ---


def test_compute_due_date_nearest():
    import time

    from telegram_bot.dialogs.viewing import compute_due_date

    now = int(time.time())
    due = compute_due_date("nearest")
    # nearest = +3 days
    assert abs(due - now - 3 * 86400) < 5


def test_compute_due_date_unknown_defaults_7_days():
    import time

    from telegram_bot.dialogs.viewing import compute_due_date

    now = int(time.time())
    due = compute_due_date("unknown")
    assert abs(due - now - 7 * 86400) < 5
