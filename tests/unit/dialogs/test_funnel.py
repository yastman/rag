"""Tests for property search funnel dialog (#697 refactor)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import telegram_bot.dialogs.funnel as funnel_module
from telegram_bot.dialogs.funnel import funnel_dialog
from telegram_bot.dialogs.states import FunnelSG


def test_funnel_dialog_exists():
    from aiogram_dialog import Dialog

    assert isinstance(funnel_dialog, Dialog)


def test_funnel_has_all_windows():
    windows = funnel_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert FunnelSG.complex in states
    assert FunnelSG.property_type in states
    assert FunnelSG.budget in states
    assert FunnelSG.preferences in states
    assert FunnelSG.pref_floor in states
    assert FunnelSG.pref_view in states
    assert FunnelSG.pref_furnished in states
    assert FunnelSG.pref_promotion in states
    assert FunnelSG.summary in states
    assert FunnelSG.change_filter in states
    assert FunnelSG.results in states


@pytest.mark.asyncio
async def test_complex_options_has_10_complexes_plus_any():
    result = await funnel_module.get_complex_options()
    items = result["items"]
    keys = [key for _, key in items]
    assert "Premier Fort Beach" in keys
    assert "any" in keys
    assert len(items) == 11  # 10 complexes + "Любой комплекс"


@pytest.mark.asyncio
async def test_preferences_options_has_4_categories_plus_done():
    result = await funnel_module.get_preferences_options(
        middleware_data={},
        dialog_manager=SimpleNamespace(dialog_data={}),
    )
    items = result["items"]
    labels = [label for label, _ in items]
    assert any("Этаж" in label for label in labels)
    assert any("Вид" in label for label in labels)
    assert any("Мебель" in label or "мебель" in label for label in labels)
    assert any("Акции" in label or "акции" in label for label in labels)


@pytest.mark.asyncio
async def test_preferences_options_shows_checkmark_when_selected():
    result = await funnel_module.get_preferences_options(
        middleware_data={},
        dialog_manager=SimpleNamespace(dialog_data={"floor": "mid", "view": "sea"}),
    )
    items = result["items"]
    labels = [label for label, _ in items]
    floor_labels = [label for label in labels if "таж" in label.lower()]
    assert any("✓" in label for label in floor_labels)


@pytest.mark.asyncio
async def test_complex_selected_saves_and_switches():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_complex_selected(
        MagicMock(), SimpleNamespace(), manager, "Premier Fort Beach"
    )
    assert manager.dialog_data["complex"] == "Premier Fort Beach"
    manager.switch_to.assert_awaited_once_with(FunnelSG.property_type)


@pytest.mark.asyncio
async def test_property_type_selected_saves_and_switches():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_property_type_selected(MagicMock(), SimpleNamespace(), manager, "studio")
    assert manager.dialog_data["property_type"] == "studio"
    manager.switch_to.assert_awaited_once_with(FunnelSG.budget)


@pytest.mark.asyncio
async def test_budget_selected_switches_to_preferences():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_budget_selected(MagicMock(), SimpleNamespace(), manager, "mid")
    assert manager.dialog_data["budget"] == "mid"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_category_floor_switches_to_pref_floor():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(MagicMock(), SimpleNamespace(), manager, "floor")
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_floor)


@pytest.mark.asyncio
async def test_pref_category_done_switches_to_summary():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(MagicMock(), SimpleNamespace(), manager, "done")
    manager.switch_to.assert_awaited_once_with(FunnelSG.summary)


@pytest.mark.asyncio
async def test_pref_floor_selected_saves_and_returns_to_preferences():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_floor_selected(MagicMock(), SimpleNamespace(), manager, "mid")
    assert manager.dialog_data["floor"] == "mid"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_furnished_selected_saves_and_returns():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_furnished_selected(MagicMock(), SimpleNamespace(), manager, "yes")
    assert manager.dialog_data["is_furnished"] == "yes"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_promotion_selected_saves_and_returns():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_promotion_selected(MagicMock(), SimpleNamespace(), manager, "yes")
    assert manager.dialog_data["is_promotion"] == "yes"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_summary_data_shows_selected_filters():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={
                "complex": "Premier Fort Beach",
                "property_type": "2bed",
                "budget": "high",
                "floor": "mid",
                "view": "sea",
            },
            middleware_data={},
        ),
    )
    assert "Premier Fort Beach" in result["summary_text"]
    assert "2-спальни" in result["summary_text"]
    assert "100 000" in result["summary_text"]
    assert "2-3 этаж" in result["summary_text"]
    assert "Море" in result["summary_text"]
    assert result["can_search"] is True


@pytest.mark.asyncio
async def test_summary_all_any_disables_search():
    """When all filters are 'any'/empty, search should be disabled."""
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={"complex": "any", "property_type": "any", "budget": "any"},
            middleware_data={},
        ),
    )
    assert result["can_search"] is False


@pytest.mark.asyncio
async def test_on_summary_search_resets_scroll_and_goes_to_results(monkeypatch):
    spawn_mock = MagicMock()
    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", spawn_mock)
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=99),
        message=SimpleNamespace(chat=SimpleNamespace(id=111)),
    )
    manager = SimpleNamespace(
        dialog_data={"complex": "Premier Fort Beach", "property_type": "2bed", "budget": "high"},
        middleware_data={
            "user_service": object(),
            "pg_pool": object(),
            "lead_scoring_store": object(),
            "kommo_client": object(),
            "hot_lead_notifier": object(),
            "bot_config": object(),
        },
        switch_to=AsyncMock(),
    )
    await funnel_module.on_summary_search(callback, SimpleNamespace(), manager)
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)
    assert manager.dialog_data.get("scroll_offset") is None


@pytest.mark.asyncio
async def test_on_summary_refine_goes_to_preferences():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_summary_refine(MagicMock(), SimpleNamespace(), manager)
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_on_summary_change_goes_to_change_filter():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_summary_change(MagicMock(), SimpleNamespace(), manager)
    manager.switch_to.assert_awaited_once_with(FunnelSG.change_filter)


@pytest.mark.asyncio
async def test_change_filter_complex_jumps_to_complex():
    manager = SimpleNamespace(dialog_data={"_return_to_summary": True}, switch_to=AsyncMock())
    await funnel_module.on_change_filter_selected(
        MagicMock(), SimpleNamespace(), manager, "complex"
    )
    manager.switch_to.assert_awaited_once_with(FunnelSG.complex)


@pytest.mark.asyncio
async def test_change_filter_sets_return_flag():
    """After selecting a filter to change, _return_to_summary flag should be set."""
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_change_filter_selected(MagicMock(), SimpleNamespace(), manager, "budget")
    assert manager.dialog_data.get("_return_to_summary") is True
    manager.switch_to.assert_awaited_once_with(FunnelSG.budget)


@pytest.mark.asyncio
async def test_complex_return_to_summary_when_flag_set():
    """When _return_to_summary is True, complex selection should return to summary."""
    manager = SimpleNamespace(dialog_data={"_return_to_summary": True}, switch_to=AsyncMock())
    await funnel_module.on_complex_selected(
        MagicMock(), SimpleNamespace(), manager, "Green Fort Suites"
    )
    assert manager.dialog_data["complex"] == "Green Fort Suites"
    assert "_return_to_summary" not in manager.dialog_data
    manager.switch_to.assert_awaited_once_with(FunnelSG.summary)


@pytest.mark.asyncio
async def test_get_results_data_calls_apartments_service():
    from telegram_bot.dialogs.funnel import get_results_data

    results = [
        {
            "id": "p1",
            "payload": {
                "complex_name": "Sunrise",
                "city": "Sunny Beach",
                "property_type": "studio",
                "floor": 2,
                "area_m2": 42,
                "view_primary": "sea",
                "view_tags": ["sea"],
                "price_eur": 48500,
                "rooms": 1,
            },
        }
    ]
    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(return_value=(results, 1, None))

    manager = SimpleNamespace(
        dialog_data={"property_type": "studio", "budget": "low"},
        middleware_data={"apartments_service": mock_svc},
    )

    result = await get_results_data(manager)
    mock_svc.scroll_with_filters.assert_awaited_once()
    assert "Sunrise" in result["results_text"]


@pytest.mark.asyncio
async def test_get_results_data_fallback_without_service():
    from telegram_bot.dialogs.funnel import get_results_data

    manager = SimpleNamespace(
        dialog_data={},
        middleware_data={},
    )

    result = await get_results_data(manager)
    assert "недоступен" in result["results_text"].lower()


@pytest.mark.asyncio
async def test_pref_furnished_any_clears_value():
    """Selecting 'any' for furnished should set is_furnished to None."""
    manager = SimpleNamespace(dialog_data={"is_furnished": "yes"}, switch_to=AsyncMock())
    await funnel_module.on_pref_furnished_selected(MagicMock(), SimpleNamespace(), manager, "any")
    assert manager.dialog_data["is_furnished"] is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_promotion_any_clears_value():
    """Selecting 'any' for promotion should set is_promotion to None."""
    manager = SimpleNamespace(dialog_data={"is_promotion": "yes"}, switch_to=AsyncMock())
    await funnel_module.on_pref_promotion_selected(MagicMock(), SimpleNamespace(), manager, "any")
    assert manager.dialog_data["is_promotion"] is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_zero_suggestion_removes_floor_and_refreshes_results():
    manager = SimpleNamespace(
        dialog_data={"floor": "mid", "scroll_offset": "off1", "scroll_next_offset": "off2"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(),
        SimpleNamespace(),
        manager,
        "rm_floor",
    )
    assert "floor" not in manager.dialog_data
    assert manager.dialog_data.get("scroll_offset") is None
    assert manager.dialog_data.get("scroll_next_offset") is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


@pytest.mark.asyncio
async def test_zero_suggestion_new_search_clears_filters_and_goes_to_complex():
    manager = SimpleNamespace(
        dialog_data={
            "complex": "Premier Fort Beach",
            "property_type": "2bed",
            "budget": "high",
            "floor": "mid",
            "view": "sea",
            "is_furnished": "yes",
            "is_promotion": "yes",
            "scroll_offset": "off1",
            "scroll_next_offset": "off2",
            "scroll_page": 2,
        },
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(),
        SimpleNamespace(),
        manager,
        "new_search",
    )
    assert manager.dialog_data == {}
    manager.switch_to.assert_awaited_once_with(FunnelSG.complex)
