# tests/unit/handlers/test_filter_panel.py
"""Tests for filter panel handler — live count recalculation (Bug 3/4 fix)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.handlers.filter_panel import (
    _get_count,
    handle_filter_panel,
)


@pytest.mark.asyncio
async def test_get_count_uses_service_when_available():
    """_get_count calls count_with_filters when service is provided."""
    svc = AsyncMock()
    svc.count_with_filters = AsyncMock(return_value=42)
    result = await _get_count({"city": "Бургас"}, {}, svc)
    assert result == 42
    svc.count_with_filters.assert_awaited_once_with(filters={"city": "Бургас"})


@pytest.mark.asyncio
async def test_get_count_falls_back_to_stale_total():
    """_get_count returns stale total when no service provided."""
    result = await _get_count({"city": "Бургас"}, {"apartment_total": 99}, None)
    assert result == 99


@pytest.mark.asyncio
async def test_get_count_falls_back_on_service_error():
    """_get_count returns stale total when service raises."""
    svc = AsyncMock()
    svc.count_with_filters = AsyncMock(side_effect=RuntimeError("db down"))
    result = await _get_count({}, {"apartment_total": 50}, svc)
    assert result == 50


@pytest.mark.asyncio
async def test_handle_set_recalculates_count():
    """_handle_set uses live count from service, not stale apartment_total."""
    from telegram_bot.callback_data import FilterPanelCB

    svc = AsyncMock()
    svc.count_with_filters = AsyncMock(return_value=15)

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "apartment_filters": {},
            "apartment_total": 100,  # stale
        }
    )
    state.update_data = AsyncMock()

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    cb_data = FilterPanelCB(action="set", field="city", value="Бургас")

    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    svc.count_with_filters.assert_awaited_once()
    # Panel text should contain the live count (15), not stale (100)
    call_text = callback.message.edit_text.call_args[0][0]
    assert "15" in call_text


@pytest.mark.asyncio
async def test_handle_reset_recalculates_count():
    """_handle_reset uses live count after clearing filters."""
    from telegram_bot.callback_data import FilterPanelCB

    svc = AsyncMock()
    svc.count_with_filters = AsyncMock(return_value=200)

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "apartment_filters": {"city": "Бургас"},
            "apartment_total": 50,
        }
    )
    state.update_data = AsyncMock()

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    cb_data = FilterPanelCB(action="reset", field="", value="")

    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    svc.count_with_filters.assert_awaited_once_with(filters={})
    call_text = callback.message.edit_text.call_args[0][0]
    assert "200" in call_text


@pytest.mark.asyncio
async def test_handle_main_recalculates_count():
    """_handle_main (back to main panel) uses live count."""
    from telegram_bot.callback_data import FilterPanelCB

    svc = AsyncMock()
    svc.count_with_filters = AsyncMock(return_value=77)

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "apartment_filters": {"rooms": 2},
            "apartment_total": 10,
        }
    )

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    cb_data = FilterPanelCB(action="main", field="", value="")

    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    svc.count_with_filters.assert_awaited_once()
    call_text = callback.message.edit_text.call_args[0][0]
    assert "77" in call_text
