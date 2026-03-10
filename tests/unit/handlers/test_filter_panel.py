# tests/unit/handlers/test_filter_panel.py
"""Tests for filter panel handler — live count recalculation (Bug 3/4 fix)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from telegram_bot.handlers.filter_panel import (
    _BUDGET_TO_PRICE,
    _coerce_value,
    _field_to_filter_key,
    _get_count,
    _price_to_budget,
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


# ============================================================
# Budget filter coercion
# ============================================================


def test_budget_field_maps_to_price_eur():
    """Budget field maps to price_eur filter key."""
    assert _field_to_filter_key("budget") == "price_eur"


@pytest.mark.parametrize(
    "budget_key,expected_range",
    [
        ("low", {"lte": 50_000}),
        ("mid", {"gte": 50_000, "lte": 100_000}),
        ("high", {"gte": 100_000, "lte": 150_000}),
        ("premium", {"gte": 150_000, "lte": 200_000}),
        ("luxury", {"gte": 200_000}),
    ],
)
def test_budget_coerce_produces_price_range(budget_key, expected_range):
    """Budget value coerces to price_eur range dict."""
    assert _coerce_value("budget", budget_key) == expected_range


def test_budget_coerce_unknown_returns_none():
    """Unknown budget value returns None."""
    assert _coerce_value("budget", "unknown") is None


def test_price_to_budget_roundtrip():
    """price_eur dict roundtrips back to budget label."""
    for label, price_range in _BUDGET_TO_PRICE.items():
        assert _price_to_budget(price_range) == label


@pytest.mark.asyncio
async def test_handle_set_budget_stores_price_eur():
    """Setting budget stores price_eur dict in apartment_filters."""
    from telegram_bot.callback_data import FilterPanelCB

    svc = AsyncMock()
    svc.count_with_filters = AsyncMock(return_value=10)

    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"apartment_filters": {}, "apartment_total": 50})
    state.update_data = AsyncMock()

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    cb_data = FilterPanelCB(action="set", field="budget", value="mid")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    # Should store price_eur, not budget
    update_kwargs = state.update_data.call_args[1]
    filters = update_kwargs["apartment_filters"]
    assert "price_eur" in filters
    assert filters["price_eur"] == {"gte": 50_000, "lte": 100_000}
    assert "budget" not in filters


@pytest.mark.asyncio
async def test_handle_set_budget_clear():
    """Setting budget to empty clears price_eur from filters."""
    from telegram_bot.callback_data import FilterPanelCB

    svc = AsyncMock()
    svc.count_with_filters = AsyncMock(return_value=99)

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "apartment_filters": {"price_eur": {"lte": 50_000}},
            "apartment_total": 50,
        }
    )
    state.update_data = AsyncMock()

    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()

    cb_data = FilterPanelCB(action="set", field="budget", value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    update_kwargs = state.update_data.call_args[1]
    filters = update_kwargs["apartment_filters"]
    assert "price_eur" not in filters
