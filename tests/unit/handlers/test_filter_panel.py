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


# Helper to build callback + state mocks for handler tests
def _make_handler_mocks(filters=None, svc_count=10):
    svc = AsyncMock()
    svc.count_with_filters = AsyncMock(return_value=svc_count)
    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={"apartment_filters": filters or {}, "apartment_total": 50}
    )
    state.update_data = AsyncMock()
    callback = AsyncMock()
    callback.message = AsyncMock()
    callback.message.edit_text = AsyncMock()
    callback.answer = AsyncMock()
    return callback, state, svc


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


# ============================================================
# All filter coercion tests
# ============================================================


@pytest.mark.parametrize(
    "field,filter_key",
    [
        ("city", "city"),
        ("rooms", "rooms"),
        ("budget", "price_eur"),
        ("view", "view_tags"),
        ("area", "area_m2"),
        ("floor", "floor"),
        ("complex", "complex_name"),
        ("furnished", "is_furnished"),
        ("promotion", "is_promotion"),
    ],
)
def test_all_field_to_filter_key_mappings(field, filter_key):
    """Every panel field maps to the correct apartment_filters key."""
    assert _field_to_filter_key(field) == filter_key


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("city", "Бургас", "Бургас"),
        ("rooms", "3", 3),
        ("floor", "5", 5),
        ("floor", "abc", None),
        ("area", "60", {"gte": 60}),
        ("area", "bad", None),
        ("view", "sea", ["sea"]),
        ("view", "", None),
        ("complex", "Harmony Suites", "Harmony Suites"),
        ("complex", "", None),
        ("furnished", "true", True),
        ("furnished", "false", False),
        ("promotion", "true", True),
        ("promotion", "false", False),
    ],
)
def test_coerce_value_all_fields(field, value, expected):
    """_coerce_value returns correct type for each field."""
    assert _coerce_value(field, value) == expected


# ============================================================
# Handler set/clear tests for all filter types
# ============================================================


@pytest.mark.parametrize(
    "field,value,expected_key,expected_value",
    [
        ("city", "Варна", "city", "Варна"),
        ("rooms", "2", "rooms", 2),
        ("floor", "3", "floor", 3),
        ("area", "50", "area_m2", {"gte": 50}),
        ("view", "sea", "view_tags", ["sea"]),
        ("complex", "Resort", "complex_name", "Resort"),
        ("furnished", "true", "is_furnished", True),
        ("promotion", "true", "is_promotion", True),
    ],
)
@pytest.mark.asyncio
async def test_handle_set_all_filters(field, value, expected_key, expected_value):
    """Setting any filter stores correct key and coerced value."""
    from telegram_bot.callback_data import FilterPanelCB

    callback, state, svc = _make_handler_mocks()
    cb_data = FilterPanelCB(action="set", field=field, value=value)
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    filters = state.update_data.call_args[1]["apartment_filters"]
    assert expected_key in filters
    assert filters[expected_key] == expected_value


@pytest.mark.parametrize(
    "field,initial_key,initial_value",
    [
        ("city", "city", "Варна"),
        ("rooms", "rooms", 2),
        ("floor", "floor", 3),
        ("area", "area_m2", {"gte": 50}),
        ("view", "view_tags", ["sea"]),
        ("complex", "complex_name", "Resort"),
        ("furnished", "is_furnished", True),
        ("promotion", "is_promotion", True),
        ("budget", "price_eur", {"lte": 50_000}),
    ],
)
@pytest.mark.asyncio
async def test_handle_clear_all_filters(field, initial_key, initial_value):
    """Clearing any filter removes the key from apartment_filters."""
    from telegram_bot.callback_data import FilterPanelCB

    callback, state, svc = _make_handler_mocks(filters={initial_key: initial_value})
    cb_data = FilterPanelCB(action="set", field=field, value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    filters = state.update_data.call_args[1]["apartment_filters"]
    assert initial_key not in filters


# ============================================================
# select action — opens sub-menu
# ============================================================


@pytest.mark.asyncio
async def test_handle_select_shows_submenu():
    """Select action edits message with sub-menu keyboard."""
    from telegram_bot.callback_data import FilterPanelCB

    callback, state, svc = _make_handler_mocks(filters={"city": "Бургас"})
    cb_data = FilterPanelCB(action="select", field="city", value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    callback.message.edit_text.assert_awaited_once()
    call_text = callback.message.edit_text.call_args[0][0]
    assert "город" in call_text.lower()
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_select_shows_current_value():
    """Select action displays current filter value in sub-menu."""
    from telegram_bot.callback_data import FilterPanelCB

    callback, state, svc = _make_handler_mocks(filters={"rooms": 3})
    cb_data = FilterPanelCB(action="select", field="rooms", value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    call_text = callback.message.edit_text.call_args[0][0]
    assert "3" in call_text


@pytest.mark.asyncio
async def test_handle_select_budget_shows_current():
    """Select budget shows current value via reverse lookup."""
    from telegram_bot.callback_data import FilterPanelCB

    callback, state, svc = _make_handler_mocks(
        filters={"price_eur": {"gte": 50_000, "lte": 100_000}}
    )
    cb_data = FilterPanelCB(action="select", field="budget", value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    call_text = callback.message.edit_text.call_args[0][0]
    assert "mid" in call_text


# ============================================================
# apply action — applies filters
# ============================================================


@pytest.mark.asyncio
async def test_handle_apply_reloads_results():
    """Apply action deletes panel, reloads results with current filters."""
    from unittest.mock import MagicMock

    from telegram_bot.callback_data import FilterPanelCB

    apt = {
        "id": "a1",
        "payload": {
            "complex_name": "X",
            "city": "Y",
            "rooms": 1,
            "floor": 1,
            "area_m2": 40,
            "view_primary": "sea",
            "price_eur": 50000,
        },
    }
    svc = AsyncMock()
    svc.count_with_filters = AsyncMock(return_value=5)
    svc.scroll_with_filters = AsyncMock(return_value=([apt] * 3, 5, 60000.0, ["a1"]))

    property_bot = MagicMock()
    property_bot._apartments_service = svc
    property_bot._send_property_card = AsyncMock()

    state = AsyncMock()
    state.get_data = AsyncMock(
        return_value={
            "apartment_filters": {"city": "Бургас"},
            "apartment_total": 50,
        }
    )
    state.update_data = AsyncMock()

    callback = AsyncMock()
    callback.from_user = MagicMock(id=123)
    callback.message = AsyncMock()
    callback.message.delete = AsyncMock()
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()

    cb_data = FilterPanelCB(action="apply", field="", value="")
    await handle_filter_panel(
        callback, state, cb_data, apartments_service=svc, property_bot=property_bot
    )

    callback.message.delete.assert_awaited_once()
    callback.answer.assert_awaited_once()
    svc.scroll_with_filters.assert_awaited_once()
    # Cards sent
    assert property_bot._send_property_card.await_count == 3
    # State updated with new offset
    update_calls = state.update_data.call_args_list
    last_update = update_calls[-1][1]
    assert last_update["apartment_offset"] == 3
    assert last_update["apartment_total"] == 5


# ============================================================
# back action — returns to catalog results
# ============================================================


@pytest.mark.asyncio
async def test_handle_back_deletes_panel():
    """Back action deletes filter panel message."""
    from telegram_bot.callback_data import FilterPanelCB

    callback, state, svc = _make_handler_mocks()
    cb_data = FilterPanelCB(action="back", field="", value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    callback.message.delete.assert_awaited_once()
    callback.answer.assert_awaited_once()


# ============================================================
# unknown action — logs warning
# ============================================================


@pytest.mark.asyncio
async def test_handle_unknown_action_answers_callback():
    """Unknown action answers callback without error."""
    from telegram_bot.callback_data import FilterPanelCB

    callback, state, svc = _make_handler_mocks()
    cb_data = FilterPanelCB(action="unknown_action", field="", value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    callback.answer.assert_awaited_once()


# ============================================================
# complex filter — dynamic options from service
# ============================================================


@pytest.mark.asyncio
async def test_handle_select_complex_loads_from_service():
    """Select complex loads dynamic options via get_collection_stats."""
    from telegram_bot.callback_data import FilterPanelCB

    svc = AsyncMock()
    svc.get_collection_stats = AsyncMock(
        return_value={"complexes": ["Premier Fort", "Harmony Suites", "Grand Resort"]}
    )

    callback, state, _ = _make_handler_mocks()
    cb_data = FilterPanelCB(action="select", field="complex", value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    svc.get_collection_stats.assert_awaited_once()
    call_text = callback.message.edit_text.call_args[0][0]
    assert "комплекс" in call_text.lower()
    # Keyboard should contain dynamic options
    kb = callback.message.edit_text.call_args[1]["reply_markup"]
    button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Premier Fort" in button_texts
    assert "Harmony Suites" in button_texts
    assert "Grand Resort" in button_texts


@pytest.mark.asyncio
async def test_handle_select_complex_current_value_checked():
    """Selected complex shows checkmark on current value."""
    from telegram_bot.callback_data import FilterPanelCB

    svc = AsyncMock()
    svc.get_collection_stats = AsyncMock(
        return_value={"complexes": ["Premier Fort", "Harmony Suites"]}
    )

    callback, state, _ = _make_handler_mocks(filters={"complex_name": "Premier Fort"})
    cb_data = FilterPanelCB(action="select", field="complex", value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    kb = callback.message.edit_text.call_args[1]["reply_markup"]
    button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "✅ Premier Fort" in button_texts
    assert "Harmony Suites" in button_texts  # no checkmark


@pytest.mark.asyncio
async def test_handle_select_complex_no_service_shows_fallback():
    """Without service, complex shows generic fallback."""
    from telegram_bot.callback_data import FilterPanelCB

    callback, state, _ = _make_handler_mocks()
    cb_data = FilterPanelCB(action="select", field="complex", value="")
    await handle_filter_panel(callback, state, cb_data, apartments_service=None)

    kb = callback.message.edit_text.call_args[1]["reply_markup"]
    button_texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "Любое" in button_texts


@pytest.mark.asyncio
async def test_handle_set_complex_stores_complex_name():
    """Setting complex stores complex_name in filters."""
    from telegram_bot.callback_data import FilterPanelCB

    callback, state, svc = _make_handler_mocks()
    cb_data = FilterPanelCB(action="set", field="complex", value="Premier Fort")
    await handle_filter_panel(callback, state, cb_data, apartments_service=svc)

    filters = state.update_data.call_args[1]["apartment_filters"]
    assert filters["complex_name"] == "Premier Fort"
