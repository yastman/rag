"""E2E flow tests for funnel — simulate full user paths through handlers."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import telegram_bot.dialogs.funnel as funnel_module
from telegram_bot.dialogs.funnel import build_funnel_filters
from telegram_bot.dialogs.states import FunnelSG


async def test_full_flow_city_type_budget_done():
    """city → type → budget → pref_done → summary."""
    data: dict = {}
    manager = SimpleNamespace(dialog_data=data, switch_to=AsyncMock())

    # Step 1: city
    await funnel_module.on_city_selected(MagicMock(), SimpleNamespace(), manager, "Элените")
    assert data["city"] == "Элените"
    manager.switch_to.assert_awaited_with(FunnelSG.property_type)

    # Step 2: type
    manager.switch_to.reset_mock()
    await funnel_module.on_property_type_selected(MagicMock(), SimpleNamespace(), manager, "2bed")
    assert data["property_type"] == "2bed"
    manager.switch_to.assert_awaited_with(FunnelSG.budget)

    # Step 3: budget
    manager.switch_to.reset_mock()
    await funnel_module.on_budget_selected(MagicMock(), SimpleNamespace(), manager, "high")
    assert data["budget"] == "high"
    manager.switch_to.assert_awaited_with(FunnelSG.preferences)

    # Step 4: skip preferences → done
    manager.switch_to.reset_mock()
    await funnel_module.on_pref_done(MagicMock(), SimpleNamespace(), manager)
    manager.switch_to.assert_awaited_with(FunnelSG.summary)

    # Verify filters
    filters = build_funnel_filters(
        city=data["city"], rooms=data["property_type"], budget=data["budget"]
    )
    assert filters == {
        "city": "Элените",
        "rooms": 3,
        "price_eur": {"gte": 100000, "lte": 150000},
    }


async def test_full_flow_with_preferences_and_section():
    """city → type → budget → floor + section → done → filters correct."""
    data: dict = {}
    manager = SimpleNamespace(dialog_data=data, switch_to=AsyncMock())

    await funnel_module.on_city_selected(MagicMock(), SimpleNamespace(), manager, "any")
    await funnel_module.on_property_type_selected(MagicMock(), SimpleNamespace(), manager, "studio")
    await funnel_module.on_budget_selected(MagicMock(), SimpleNamespace(), manager, "low")

    # Preferences: floor + section
    await funnel_module.on_pref_floor_selected(MagicMock(), SimpleNamespace(), manager, "high")
    await funnel_module.on_pref_section_selected(MagicMock(), SimpleNamespace(), manager, "D-1")
    await funnel_module.on_pref_done(MagicMock(), SimpleNamespace(), manager)

    filters = build_funnel_filters(
        city=data.get("city"),
        rooms=data.get("property_type", "any"),
        budget=data.get("budget", "any"),
        floor=data.get("floor"),
        section=data.get("section"),
    )
    assert filters == {
        "rooms": [0, 1],
        "price_eur": {"lte": 50000},
        "floor": {"gte": 4, "lte": 5},
        "section": "D-1",
    }


async def test_change_filter_flow_returns_to_summary():
    """change_filter → city → re-select → back to summary."""
    data: dict = {"city": "Элените", "property_type": "1bed", "budget": "mid"}
    manager = SimpleNamespace(dialog_data=data, switch_to=AsyncMock())

    # Enter change mode
    await funnel_module.on_change_filter_selected(MagicMock(), SimpleNamespace(), manager, "city")
    assert data["_return_to_summary"] is True
    manager.switch_to.assert_awaited_with(FunnelSG.city)

    # Re-select city → should return to summary
    manager.switch_to.reset_mock()
    await funnel_module.on_city_selected(MagicMock(), SimpleNamespace(), manager, "Свети Влас")
    assert data["city"] == "Свети Влас"
    assert "_return_to_summary" not in data
    manager.switch_to.assert_awaited_with(FunnelSG.summary)


async def test_zero_results_recovery_removes_filter():
    """Zero results → rm_floor → results refreshed with fewer filters."""
    data: dict = {
        "city": "Элените",
        "property_type": "2bed",
        "budget": "luxury",
        "floor": "top",
        "scroll_offset": "off1",
        "scroll_next_offset": "off2",
    }
    manager = SimpleNamespace(dialog_data=data, switch_to=AsyncMock())

    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_floor"
    )
    assert "floor" not in data
    assert data.get("scroll_offset") is None
    manager.switch_to.assert_awaited_with(FunnelSG.results)

    # Verify filters without floor
    filters = build_funnel_filters(
        city=data.get("city"),
        rooms=data.get("property_type", "any"),
        budget=data.get("budget", "any"),
        floor=data.get("floor"),
    )
    assert "floor" not in filters
    assert filters["city"] == "Элените"
