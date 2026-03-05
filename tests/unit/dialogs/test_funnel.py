"""Tests for property search funnel dialog (#697 refactor, #712 city filter)."""

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

import telegram_bot.dialogs.funnel as funnel_module
from telegram_bot.dialogs.funnel import funnel_dialog
from telegram_bot.dialogs.states import FunnelSG


# --- build_funnel_filters ---


def test_build_funnel_filters_includes_city():
    from telegram_bot.dialogs.funnel import build_funnel_filters

    filters = build_funnel_filters(city="Солнечный берег", rooms="1bed", budget="mid")
    assert filters["city"] == "Солнечный берег"
    assert filters["rooms"] == 2
    assert "price_eur" in filters


def test_build_funnel_filters_skips_city_any():
    from telegram_bot.dialogs.funnel import build_funnel_filters

    filters = build_funnel_filters(city="any", rooms="1bed")
    assert "city" not in filters


def test_build_funnel_filters_includes_area_range():
    from telegram_bot.dialogs.funnel import build_funnel_filters

    filters = build_funnel_filters(rooms="1bed", budget="mid", area="large")
    assert filters["area_m2"] == {"gte": 60, "lte": 80}


def test_build_funnel_filters_skips_area_any():
    from telegram_bot.dialogs.funnel import build_funnel_filters

    filters = build_funnel_filters(rooms="1bed", budget="mid", area="any")
    assert "area_m2" not in filters


def test_build_funnel_filters_skips_area_none():
    from telegram_bot.dialogs.funnel import build_funnel_filters

    filters = build_funnel_filters(rooms="1bed", budget="mid", area=None)
    assert "area_m2" not in filters


# --- Dialog structure ---


def test_funnel_dialog_exists():
    from aiogram_dialog import Dialog

    assert isinstance(funnel_dialog, Dialog)


def test_funnel_has_all_windows():
    windows = funnel_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert FunnelSG.city in states
    assert FunnelSG.property_type in states
    assert FunnelSG.budget in states
    assert FunnelSG.preferences in states
    assert FunnelSG.pref_floor in states
    assert FunnelSG.pref_view in states
    assert FunnelSG.pref_furnished in states
    assert FunnelSG.pref_promotion in states
    assert FunnelSG.pref_area in states
    assert FunnelSG.pref_complex in states
    assert FunnelSG.summary in states
    assert FunnelSG.change_filter in states
    assert FunnelSG.results in states


# --- City getter/handler ---


@pytest.mark.asyncio
async def test_city_options_has_3_cities_plus_any():
    result = await funnel_module.get_city_options()
    items = result["items"]
    keys = [key for _, key in items]
    assert "Солнечный берег" in keys
    assert "Свети Влас" in keys
    assert "Элените" in keys
    assert "any" in keys
    assert len(items) == 4


@pytest.mark.asyncio
async def test_city_selected_saves_and_switches_to_property_type():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_city_selected(MagicMock(), SimpleNamespace(), manager, "Солнечный берег")
    assert manager.dialog_data["city"] == "Солнечный берег"
    manager.switch_to.assert_awaited_once_with(FunnelSG.property_type)


@pytest.mark.asyncio
async def test_city_return_to_summary_when_flag_set():
    manager = SimpleNamespace(dialog_data={"_return_to_summary": True}, switch_to=AsyncMock())
    await funnel_module.on_city_selected(MagicMock(), SimpleNamespace(), manager, "Элените")
    assert manager.dialog_data["city"] == "Элените"
    assert "_return_to_summary" not in manager.dialog_data
    manager.switch_to.assert_awaited_once_with(FunnelSG.summary)


# --- pref_complex getter/handler ---


@pytest.mark.asyncio
async def test_pref_complex_options_has_10_complexes_plus_any():
    result = await funnel_module.get_pref_complex_options(
        middleware_data={},
        dialog_manager=SimpleNamespace(dialog_data={}),
    )
    items = result["items"]
    keys = [key for _, key in items]
    assert "Premier Fort Beach" in keys
    assert "any" in keys
    assert len(items) == 11  # 10 complexes + "Любой"


@pytest.mark.asyncio
async def test_pref_complex_selected_saves_and_returns_to_preferences():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_complex_selected(
        MagicMock(), SimpleNamespace(), manager, "Premier Fort Beach"
    )
    assert manager.dialog_data["complex"] == "Premier Fort Beach"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_complex_any_clears_value():
    manager = SimpleNamespace(dialog_data={"complex": "Premier Fort Beach"}, switch_to=AsyncMock())
    await funnel_module.on_pref_complex_selected(MagicMock(), SimpleNamespace(), manager, "any")
    assert manager.dialog_data["complex"] is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


# --- Preferences menu ---


@pytest.mark.asyncio
async def test_preferences_options_has_7_categories():
    """Preferences getter returns 7 category items (6 original + section)."""
    result = await funnel_module.get_preferences_options(
        middleware_data={},
        dialog_manager=SimpleNamespace(dialog_data={}),
    )
    items = result["items"]
    assert result["title"] == "✨ Есть ли дополнительные пожелания?"
    ids = [item_id for _, item_id in items]
    assert "floor" in ids
    assert "view" in ids
    assert "area" in ids
    assert "furnished" in ids
    assert "promotion" in ids
    assert "complex" in ids
    assert "section" in ids
    assert "done" not in ids  # "done" is now a separate Button widget
    assert len(items) == 7


@pytest.mark.asyncio
async def test_preferences_options_uses_emoji_labels_for_all_categories():
    result = await funnel_module.get_preferences_options(
        middleware_data={},
        dialog_manager=SimpleNamespace(dialog_data={}),
    )
    labels_by_id = {item_id: label for label, item_id in result["items"]}

    assert labels_by_id["floor"] == "🏢 Этаж"
    assert labels_by_id["view"] == "🌅 Вид"
    assert labels_by_id["area"] == "📐 Площадь"
    assert labels_by_id["furnished"] == "🛋 Мебель"
    assert labels_by_id["promotion"] == "🏷 Акции"
    assert labels_by_id["complex"] == "🏘 Комплекс"
    assert labels_by_id["section"] == "📍 Секция"


@pytest.mark.asyncio
async def test_preferences_options_syncs_widget_state_when_selected():
    """get_preferences_options syncs Multiselect widget_data from dialog_data."""
    widget_data: dict[str, Any] = {}
    ctx = SimpleNamespace(widget_data=widget_data)
    manager = SimpleNamespace(
        dialog_data={"floor": "mid", "view": "sea"},
        current_context=lambda: ctx,
    )
    await funnel_module.get_preferences_options(middleware_data={}, dialog_manager=manager)
    checked = widget_data.get(funnel_module._PREF_MS_ID, [])
    assert "floor" in checked
    assert "view" in checked
    assert "area" not in checked


@pytest.mark.asyncio
async def test_preferences_complex_syncs_widget_state_when_selected():
    """get_preferences_options marks 'complex' as checked in widget_data when complex is set."""
    widget_data: dict[str, Any] = {}
    ctx = SimpleNamespace(widget_data=widget_data)
    manager = SimpleNamespace(
        dialog_data={"complex": "Premier Fort Beach"},
        current_context=lambda: ctx,
    )
    await funnel_module.get_preferences_options(middleware_data={}, dialog_manager=manager)
    checked = widget_data.get(funnel_module._PREF_MS_ID, [])
    assert "complex" in checked


@pytest.mark.asyncio
async def test_pref_category_complex_switches_to_pref_complex():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(
        MagicMock(), SimpleNamespace(), manager, "complex"
    )
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_complex)


# --- pref_area getter/handler ---


@pytest.mark.asyncio
async def test_pref_area_options_has_5_buckets_plus_any():
    result = await funnel_module.get_pref_area_options(
        middleware_data={},
        dialog_manager=SimpleNamespace(dialog_data={}),
    )
    items = result["items"]
    keys = [key for _, key in items]
    assert "small" in keys
    assert "mid" in keys
    assert "large" in keys
    assert "xlarge" in keys
    assert "xxlarge" in keys
    assert "any" in keys
    assert len(items) == 6
    assert result["title"] == "Какую площадь предпочитаете?"


@pytest.mark.asyncio
async def test_pref_area_selected_saves_and_returns_to_preferences():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_area_selected(MagicMock(), SimpleNamespace(), manager, "large")
    assert manager.dialog_data["area"] == "large"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_area_any_clears_value():
    manager = SimpleNamespace(dialog_data={"area": "large"}, switch_to=AsyncMock())
    await funnel_module.on_pref_area_selected(MagicMock(), SimpleNamespace(), manager, "any")
    assert manager.dialog_data["area"] is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_category_area_switches_to_pref_area():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(MagicMock(), SimpleNamespace(), manager, "area")
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_area)


# --- Other step handlers (unchanged) ---


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
async def test_pref_done_switches_to_summary():
    """The dedicated 'done' button handler navigates to summary."""
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_done(MagicMock(), SimpleNamespace(), manager)
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


# --- Summary ---


@pytest.mark.asyncio
async def test_summary_data_shows_city():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={"city": "Солнечный берег", "property_type": "1bed", "budget": "mid"},
            middleware_data={},
        ),
    )
    assert "Солнечный берег" in result["summary_text"]
    assert result["can_search"] is True


@pytest.mark.asyncio
async def test_summary_city_any_not_shown():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={"city": "any", "property_type": "1bed", "budget": "mid"},
            middleware_data={},
        ),
    )
    assert "Город: Любой" in result["summary_text"]


@pytest.mark.asyncio
async def test_summary_shows_complex_from_preferences():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={
                "city": "Солнечный берег",
                "complex": "Premier Fort Beach",
                "property_type": "2bed",
                "budget": "high",
            },
            middleware_data={},
        ),
    )
    assert "Premier Fort Beach" in result["summary_text"]
    assert "Солнечный берег" in result["summary_text"]


@pytest.mark.asyncio
async def test_summary_data_shows_selected_filters():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={
                "city": "Солнечный берег",
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
async def test_summary_shows_area():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={
                "city": "Солнечный берег",
                "property_type": "1bed",
                "budget": "mid",
                "area": "large",
            },
            middleware_data={},
        ),
    )
    assert "60–80 m²" in result["summary_text"]


@pytest.mark.asyncio
async def test_summary_all_any_allows_search_and_shows_explicit_any_labels():
    """Summary always allows search and shows explicit 'Любой' core filters (#722)."""
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={"city": "any", "property_type": "any", "budget": "any"},
            middleware_data={},
        ),
    )
    assert "Город: Любой" in result["summary_text"]
    assert "Тип: Любой" in result["summary_text"]
    assert "Бюджет: Любой" in result["summary_text"]
    assert result["can_search"] is True


# --- Summary actions ---


@pytest.mark.asyncio
async def test_on_summary_search_resets_scroll_and_goes_to_results(monkeypatch):
    spawn_mock = MagicMock()
    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", spawn_mock)
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=99),
        message=SimpleNamespace(chat=SimpleNamespace(id=111)),
    )
    manager = SimpleNamespace(
        dialog_data={
            "city": "Солнечный берег",
            "property_type": "2bed",
            "budget": "high",
        },
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


def test_switchto_change_in_summary_targets_change_filter():
    """SwitchTo 'change' in summary window targets FunnelSG.change_filter."""
    from aiogram_dialog.widgets.kbd import SwitchTo as SwitchToWidget

    summary_window = funnel_dialog.windows[FunnelSG.summary]
    found = False
    for widget in summary_window.keyboard.buttons:
        if isinstance(widget, SwitchToWidget) and widget.widget_id == "change":
            assert widget.state == FunnelSG.change_filter
            found = True
            break
    assert found, "SwitchTo 'change' not found in summary window"


def test_switchto_refine_in_summary_targets_preferences():
    """SwitchTo 'refine' in summary window targets FunnelSG.preferences."""
    from aiogram_dialog.widgets.kbd import SwitchTo as SwitchToWidget

    summary_window = funnel_dialog.windows[FunnelSG.summary]
    found = False
    for widget in summary_window.keyboard.buttons:
        if isinstance(widget, SwitchToWidget) and widget.widget_id == "refine":
            assert widget.state == FunnelSG.preferences
            found = True
            break
    assert found, "SwitchTo 'refine' not found in summary window"


# --- Change filter ---


@pytest.mark.asyncio
async def test_change_filter_includes_city():
    result = await funnel_module.get_change_filter_options()
    items_ids = [item_id for _, item_id in result["items"]]
    assert "city" in items_ids


@pytest.mark.asyncio
async def test_change_filter_city_jumps_to_city():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_change_filter_selected(MagicMock(), SimpleNamespace(), manager, "city")
    assert manager.dialog_data.get("_return_to_summary") is True
    manager.switch_to.assert_awaited_once_with(FunnelSG.city)


@pytest.mark.asyncio
async def test_change_filter_sets_return_flag():
    """After selecting a filter to change, _return_to_summary flag should be set."""
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_change_filter_selected(MagicMock(), SimpleNamespace(), manager, "budget")
    assert manager.dialog_data.get("_return_to_summary") is True
    manager.switch_to.assert_awaited_once_with(FunnelSG.budget)


# --- Results ---


@pytest.mark.asyncio
async def test_get_results_data_calls_apartments_service():
    from telegram_bot.dialogs.funnel import get_results_data

    results = [
        {
            "id": "p1",
            "payload": {
                "complex_name": "Sunrise",
                "city": "Солнечный берег",
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


# --- Preference any clears ---


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


# --- Zero suggestions ---


@pytest.mark.asyncio
async def test_zero_suggestion_removes_area_and_refreshes_results():
    manager = SimpleNamespace(
        dialog_data={"area": "large", "scroll_offset": "off1", "scroll_next_offset": "off2"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_area"
    )
    assert "area" not in manager.dialog_data
    assert manager.dialog_data.get("scroll_offset") is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


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
async def test_on_summary_search_sends_photo_cards_and_closes_dialog(monkeypatch):
    """on_summary_search should search, send cards via property_bot, then close dialog."""
    spawn_mock = MagicMock()
    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", spawn_mock)

    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(
        return_value=(
            [
                {
                    "id": "apt-1",
                    "payload": {
                        "complex_name": "Test",
                        "city": "Бургас",
                        "property_type": "Студия",
                        "floor": 2,
                        "area_m2": 45,
                        "view_tags": [],
                        "view_primary": "sea",
                        "price_eur": 55000,
                        "rooms": 1,
                    },
                },
            ],
            1,
            None,
        )
    )
    mock_bot = MagicMock()
    mock_bot._send_property_card = AsyncMock()
    mock_bot._apartments_service = mock_svc

    callback = MagicMock()
    callback.from_user = MagicMock(id=123)
    callback.message = MagicMock()
    callback.message.chat = MagicMock(id=456)
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()

    manager = MagicMock()
    manager.dialog_data = {"city": "Бургас", "property_type": "1bed", "budget": "mid"}
    manager.middleware_data = {
        "apartments_service": mock_svc,
        "property_bot": mock_bot,
        "state": MagicMock(update_data=AsyncMock()),
    }
    manager.done = AsyncMock()

    await funnel_module.on_summary_search(callback, MagicMock(), manager)

    mock_bot._send_property_card.assert_awaited_once()
    manager.done.assert_awaited_once()


@pytest.mark.asyncio
async def test_zero_suggestion_new_search_clears_all_and_goes_to_city():
    manager = SimpleNamespace(
        dialog_data={
            "city": "Солнечный берег",
            "complex": "Premier Fort Beach",
            "property_type": "2bed",
            "budget": "high",
            "floor": "mid",
            "view": "sea",
            "area": "large",
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
    manager.switch_to.assert_awaited_once_with(FunnelSG.city)


# ============================================================
# Task 1: Handler & navigation tests (existing code coverage)
# ============================================================


@pytest.mark.asyncio
async def test_pref_view_selected_saves_and_returns():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_view_selected(MagicMock(), SimpleNamespace(), manager, "sea")
    assert manager.dialog_data["view"] == "sea"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_view_any_keeps_any_marker():
    manager = SimpleNamespace(dialog_data={"view": "sea"}, switch_to=AsyncMock())
    await funnel_module.on_pref_view_selected(MagicMock(), SimpleNamespace(), manager, "any")
    assert manager.dialog_data["view"] == "any"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_category_view_switches_to_pref_view():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(MagicMock(), SimpleNamespace(), manager, "view")
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_view)


@pytest.mark.asyncio
async def test_pref_category_furnished_switches_to_pref_furnished():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(
        MagicMock(), SimpleNamespace(), manager, "furnished"
    )
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_furnished)


@pytest.mark.asyncio
async def test_pref_category_promotion_switches_to_pref_promotion():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(
        MagicMock(), SimpleNamespace(), manager, "promotion"
    )
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_promotion)


def test_switchto_back_in_pref_floor_targets_preferences():
    """SwitchTo back button in pref_floor targets FunnelSG.preferences."""
    from aiogram_dialog.widgets.kbd import SwitchTo as SwitchToWidget

    floor_window = funnel_dialog.windows[FunnelSG.pref_floor]
    found = False
    for widget in floor_window.keyboard.buttons:
        if isinstance(widget, SwitchToWidget) and widget.widget_id == "pref_floor_back":
            assert widget.state == FunnelSG.preferences
            found = True
            break
    assert found, "SwitchTo 'pref_floor_back' not found in pref_floor window"


@pytest.mark.asyncio
async def test_results_more_increments_page_and_offset():
    manager = SimpleNamespace(
        dialog_data={"scroll_next_offset": "uuid-next", "scroll_page": 1},
    )
    callback = MagicMock()
    callback.answer = AsyncMock()
    await funnel_module.on_results_more(callback, SimpleNamespace(), manager)
    assert manager.dialog_data["scroll_offset"] == "uuid-next"
    assert manager.dialog_data["scroll_page"] == 2


@pytest.mark.asyncio
async def test_results_more_no_next_offset_answers_all_shown():
    manager = SimpleNamespace(dialog_data={})
    callback = MagicMock()
    callback.answer = AsyncMock()
    await funnel_module.on_results_more(callback, SimpleNamespace(), manager)
    callback.answer.assert_awaited_once_with("Все результаты показаны")


@pytest.mark.asyncio
async def test_property_type_return_to_summary():
    manager = SimpleNamespace(dialog_data={"_return_to_summary": True}, switch_to=AsyncMock())
    await funnel_module.on_property_type_selected(MagicMock(), SimpleNamespace(), manager, "2bed")
    assert manager.dialog_data["property_type"] == "2bed"
    assert "_return_to_summary" not in manager.dialog_data
    manager.switch_to.assert_awaited_once_with(FunnelSG.summary)


# ============================================================
# Task 2: Getters, zero suggestions, summary display
# ============================================================


@pytest.mark.asyncio
async def test_pref_floor_options_has_4_plus_any():
    result = await funnel_module.get_pref_floor_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert len(items) == 5
    assert set(keys) == {"low", "mid", "high", "top", "any"}


@pytest.mark.asyncio
async def test_pref_view_options_has_4_plus_any():
    result = await funnel_module.get_pref_view_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert len(items) == 5
    assert set(keys) == {"sea", "pool", "garden", "forest", "any"}


@pytest.mark.asyncio
async def test_pref_furnished_options_has_3():
    result = await funnel_module.get_pref_furnished_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert len(items) == 3
    assert set(keys) == {"yes", "no", "any"}


@pytest.mark.asyncio
async def test_pref_promotion_options_has_2():
    result = await funnel_module.get_pref_promotion_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert len(items) == 2
    assert set(keys) == {"yes", "any"}


@pytest.mark.asyncio
async def test_zero_suggestion_rm_view():
    manager = SimpleNamespace(
        dialog_data={"view": "sea", "scroll_offset": "x", "scroll_next_offset": "y"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_view"
    )
    assert "view" not in manager.dialog_data
    assert manager.dialog_data.get("scroll_offset") is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


@pytest.mark.asyncio
async def test_zero_suggestion_rm_furnished():
    manager = SimpleNamespace(
        dialog_data={"is_furnished": "yes", "scroll_offset": "x"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_furnished"
    )
    assert "is_furnished" not in manager.dialog_data
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


@pytest.mark.asyncio
async def test_zero_suggestion_rm_promotion():
    manager = SimpleNamespace(
        dialog_data={"is_promotion": "yes", "scroll_offset": "x"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_promotion"
    )
    assert "is_promotion" not in manager.dialog_data
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


@pytest.mark.asyncio
async def test_zero_suggestion_rm_budget():
    manager = SimpleNamespace(
        dialog_data={"budget": "high", "scroll_offset": "x"},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_budget"
    )
    assert manager.dialog_data["budget"] == "any"
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


@pytest.mark.asyncio
async def test_summary_shows_furnished_yes():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={
                "city": "any",
                "property_type": "any",
                "budget": "any",
                "is_furnished": "yes",
            },
            middleware_data={},
        ),
    )
    assert "С мебелью" in result["summary_text"]


@pytest.mark.asyncio
async def test_summary_shows_furnished_no():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={
                "city": "any",
                "property_type": "any",
                "budget": "any",
                "is_furnished": "no",
            },
            middleware_data={},
        ),
    )
    assert "Без мебели" in result["summary_text"]


@pytest.mark.asyncio
async def test_summary_shows_promotion():
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={
                "city": "any",
                "property_type": "any",
                "budget": "any",
                "is_promotion": "yes",
            },
            middleware_data={},
        ),
    )
    assert "Акции" in result["summary_text"]


# ============================================================
# Task 5: Section filter tests
# ============================================================


@pytest.mark.asyncio
async def test_pref_section_options_has_sections_plus_any():
    result = await funnel_module.get_pref_section_options(middleware_data={})
    items = result["items"]
    keys = [key for _, key in items]
    assert "D-1" in keys
    assert "any" in keys
    assert len(items) == 27  # 26 unique sections from CSV + "any"


@pytest.mark.asyncio
async def test_pref_section_selected_saves_and_returns():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_section_selected(MagicMock(), SimpleNamespace(), manager, "D-1")
    assert manager.dialog_data["section"] == "D-1"
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_section_any_clears_value():
    manager = SimpleNamespace(dialog_data={"section": "D-1"}, switch_to=AsyncMock())
    await funnel_module.on_pref_section_selected(MagicMock(), SimpleNamespace(), manager, "any")
    assert manager.dialog_data["section"] is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.preferences)


@pytest.mark.asyncio
async def test_pref_category_section_switches_to_pref_section():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())
    await funnel_module.on_pref_category_selected(
        MagicMock(), SimpleNamespace(), manager, "section"
    )
    manager.switch_to.assert_awaited_once_with(FunnelSG.pref_section)


@pytest.mark.asyncio
async def test_preferences_section_syncs_widget_state():
    widget_data: dict[str, Any] = {}
    ctx = SimpleNamespace(widget_data=widget_data)
    manager = SimpleNamespace(
        dialog_data={"section": "D-1"},
        current_context=lambda: ctx,
    )
    await funnel_module.get_preferences_options(middleware_data={}, dialog_manager=manager)
    checked = widget_data.get(funnel_module._PREF_MS_ID, [])
    assert "section" in checked


def test_funnel_has_pref_section_window():
    windows = funnel_dialog.windows
    states = [w.get_state() for w in windows.values()]
    assert FunnelSG.pref_section in states
