"""Tests for FilterDialog — aiogram-dialog based filter panel."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from telegram_bot.dialogs.states import FilterSG


# ============================================================
# FilterSG states
# ============================================================


class TestFilterSGStates:
    def test_has_hub_state(self):
        assert hasattr(FilterSG, "hub")

    def test_has_city_state(self):
        assert hasattr(FilterSG, "city")

    def test_has_rooms_state(self):
        assert hasattr(FilterSG, "rooms")

    def test_has_budget_state(self):
        assert hasattr(FilterSG, "budget")

    def test_has_view_state(self):
        assert hasattr(FilterSG, "view")

    def test_has_area_state(self):
        assert hasattr(FilterSG, "area")

    def test_has_floor_state(self):
        assert hasattr(FilterSG, "floor")

    def test_has_complex_state(self):
        assert hasattr(FilterSG, "complex_name")

    def test_has_furnished_state(self):
        assert hasattr(FilterSG, "furnished")

    def test_has_promotion_state(self):
        assert hasattr(FilterSG, "promotion")


# ============================================================
# FilterDialog structure
# ============================================================


class TestFilterDialogStructure:
    def test_filter_dialog_importable(self):
        from telegram_bot.dialogs.filter_dialog import filter_dialog  # noqa: F401

    def test_filter_dialog_is_dialog(self):
        from aiogram_dialog import Dialog

        from telegram_bot.dialogs.filter_dialog import filter_dialog

        assert isinstance(filter_dialog, Dialog)

    def test_filter_dialog_has_hub_window(self):
        from telegram_bot.dialogs.filter_dialog import filter_dialog

        state_names = {s.state.split(":")[-1] for s in filter_dialog.windows}
        assert "hub" in state_names

    def test_filter_dialog_covers_all_filter_states(self):
        from telegram_bot.dialogs.filter_dialog import filter_dialog

        state_names = {s.state.split(":")[-1] for s in filter_dialog.windows}
        required = {
            "hub",
            "city",
            "rooms",
            "budget",
            "view",
            "area",
            "floor",
            "complex_name",
            "furnished",
            "promotion",
        }
        assert required == state_names

    def test_filter_windows_use_radio_widgets(self):
        """All filter sub-windows should use Radio (not Select) for checked indicators."""
        from aiogram_dialog.widgets.kbd import Radio

        from telegram_bot.dialogs.filter_dialog import filter_dialog

        for window_state in filter_dialog.windows:
            state_name = window_state.state.split(":")[-1]
            if state_name == "hub":
                continue  # hub has no Radio
            # Walk widget tree to find Radio
            found_radio = False
            for widget in _iter_widgets(filter_dialog.windows[window_state]):
                if isinstance(widget, Radio):
                    found_radio = True
                    break
            assert found_radio, f"Window '{state_name}' should use Radio widget"

    def test_filter_subwindows_have_back_button(self):
        """All filter sub-windows should have a SwitchTo back button to hub."""
        from aiogram_dialog.widgets.kbd import SwitchTo

        from telegram_bot.dialogs.filter_dialog import filter_dialog

        for window_state in filter_dialog.windows:
            state_name = window_state.state.split(":")[-1]
            if state_name == "hub":
                continue
            found_back = False
            for widget in _iter_widgets(filter_dialog.windows[window_state]):
                if isinstance(widget, SwitchTo):
                    target = widget.state.state.split(":")[-1] if widget.state else ""
                    if target == "hub":
                        found_back = True
                        break
            assert found_back, f"Window '{state_name}' should have a back button to hub"


def _iter_widgets(window):
    """Recursively iterate all widgets in a Window."""

    if hasattr(window, "keyboard"):
        kbd = window.keyboard
        if kbd is not None:
            yield from _iter_kbd_widgets(kbd)


def _iter_kbd_widgets(widget):
    """Recursively yield keyboard widgets."""
    yield widget
    if hasattr(widget, "buttons"):
        for btn in widget.buttons:
            yield from _iter_kbd_widgets(btn)
    if hasattr(widget, "widgets"):
        for w in widget.widgets:
            yield from _iter_kbd_widgets(w)


# ============================================================
# Hub getter — get_hub_data
# ============================================================


class TestGetHubData:
    async def test_returns_count(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        svc = AsyncMock()
        svc.count_with_filters = AsyncMock(return_value=42)
        manager = SimpleNamespace(
            dialog_data={},
            middleware_data={"apartments_service": svc},
        )
        result = await get_hub_data(dialog_manager=manager)
        assert result["count"] == 42

    async def test_count_falls_back_to_zero_without_service(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        manager = SimpleNamespace(
            dialog_data={},
            middleware_data={"apartments_service": None},
        )
        result = await get_hub_data(dialog_manager=manager)
        assert result["count"] == 0

    async def test_returns_active_filters_text(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        manager = SimpleNamespace(
            dialog_data={"city": "Бургас", "rooms": "3", "budget": "mid"},
            middleware_data={"apartments_service": None},
        )
        result = await get_hub_data(dialog_manager=manager)
        text = result["active_filters"]
        assert "Бургас" in text
        assert "2-спальни" in text
        assert "50 000" in text

    async def test_empty_filters_show_no_filters(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        manager = SimpleNamespace(
            dialog_data={},
            middleware_data={"apartments_service": None},
        )
        result = await get_hub_data(dialog_manager=manager)
        assert result["active_filters"] == "Фильтры не заданы"


# ============================================================
# on_apply — saves filters to FSMContext and closes dialog
# ============================================================


def _make_apply_mocks(
    dialog_data=None,
    *,
    fsm_data=None,
    apartments_service=None,
    property_bot=None,
):
    """Create callback + manager mocks for on_apply tests."""
    state = AsyncMock()
    state.get_data = AsyncMock(return_value=fsm_data or {})
    state.update_data = AsyncMock()

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.message.delete = AsyncMock()

    manager = AsyncMock()
    manager.dialog_data = dialog_data or {}
    manager.middleware_data = {
        "state": state,
        "apartments_service": apartments_service,
        "property_bot": property_bot,
    }
    manager.done = AsyncMock()
    manager.start = AsyncMock()

    return callback, state, manager


class TestOnApply:
    async def test_saves_filters_to_fsm(self):
        from telegram_bot.dialogs.filter_dialog import on_apply

        callback, state, manager = _make_apply_mocks({"city": "Несебр", "budget": "mid"})
        await on_apply(callback, MagicMock(), manager)

        assert state.update_data.await_count >= 1
        call_kwargs = state.update_data.await_args_list[0].kwargs
        runtime = call_kwargs["catalog_runtime"]
        filters = runtime["filters"]
        assert filters["city"] == "Несебр"
        assert "price_eur" in filters
        assert "budget" not in filters

    async def test_starts_catalog_dialog_results(self):
        from aiogram_dialog import ShowMode, StartMode

        from telegram_bot.dialogs.filter_dialog import on_apply
        from telegram_bot.dialogs.states import CatalogSG

        callback, _state, manager = _make_apply_mocks()
        await on_apply(callback, MagicMock(), manager)

        manager.start.assert_awaited_once_with(
            CatalogSG.empty,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.NO_UPDATE,
        )

    async def test_resets_catalog_runtime_pagination(self):
        from telegram_bot.dialogs.filter_dialog import on_apply

        callback, state, manager = _make_apply_mocks({"city": "Варна"})
        await on_apply(callback, MagicMock(), manager)

        call_kwargs = state.update_data.call_args[1]
        runtime = call_kwargs["catalog_runtime"]
        assert runtime.get("shown_count") == 0

    async def test_empty_results_use_catalog_empty_state(self):
        from aiogram_dialog import ShowMode, StartMode

        from telegram_bot.dialogs.filter_dialog import on_apply
        from telegram_bot.dialogs.states import CatalogSG

        callback, _state, manager = _make_apply_mocks({"city": "Бургас"})
        await on_apply(callback, MagicMock(), manager)

        manager.start.assert_awaited_once_with(
            CatalogSG.empty,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.NO_UPDATE,
        )

    async def test_closes_and_deletes_filter_shell_before_catalog_results(self):
        from aiogram_dialog import ShowMode, StartMode

        from telegram_bot.dialogs.filter_dialog import on_apply
        from telegram_bot.dialogs.states import CatalogSG

        svc = AsyncMock()
        svc.scroll_with_filters = AsyncMock(
            return_value=([{"id": "apt-1", "payload": {}}], 1, None, ["apt-1"])
        )
        callback, _state, manager = _make_apply_mocks(
            {"city": "Варна"},
            fsm_data={"catalog_runtime": {"view_mode": "list"}},
            apartments_service=svc,
        )

        await on_apply(callback, MagicMock(), manager)

        assert manager.show_mode == ShowMode.NO_UPDATE
        manager.done.assert_awaited_once()
        callback.message.delete.assert_awaited_once()
        manager.start.assert_awaited_once_with(
            CatalogSG.results,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.NO_UPDATE,
        )

    async def test_closes_and_deletes_filter_shell_before_catalog_results(self):
        from aiogram_dialog import ShowMode, StartMode

        from telegram_bot.dialogs.filter_dialog import on_apply
        from telegram_bot.dialogs.states import CatalogSG

        svc = AsyncMock()
        svc.scroll_with_filters = AsyncMock(
            return_value=([{"id": "apt-1", "payload": {}}], 1, None, ["apt-1"])
        )
        callback, _state, manager = _make_apply_mocks(
            {"city": "Варна"},
            fsm_data={"catalog_runtime": {"view_mode": "list"}},
            apartments_service=svc,
        )

        await on_apply(callback, MagicMock(), manager)

        assert manager.show_mode == ShowMode.NO_UPDATE
        manager.done.assert_awaited_once()
        callback.message.delete.assert_awaited_once()
        manager.start.assert_awaited_once_with(
            CatalogSG.results,
            mode=StartMode.RESET_STACK,
            show_mode=ShowMode.NO_UPDATE,
        )


# ============================================================
# on_reset — clears dialog_data filters
# ============================================================


class TestOnReset:
    async def test_clears_all_filter_fields(self):
        from telegram_bot.dialogs.filter_dialog import on_reset

        manager = AsyncMock()
        manager.dialog_data = {"city": "Варна", "budget": "mid", "rooms": 2}
        widget_data = {"r_city": "Варна", "r_budget": "mid", "r_rooms": "2"}
        manager.current_context = MagicMock(return_value=SimpleNamespace(widget_data=widget_data))
        manager.find = MagicMock(return_value=AsyncMock(set_checked=AsyncMock()))

        await on_reset(MagicMock(), MagicMock(), manager)

        for field in ("city", "budget", "rooms"):
            assert manager.dialog_data.get(field) is None or field not in manager.dialog_data
        assert widget_data == {}


# ============================================================
# on_filter_dialog_start — clears stale state on reopen
# ============================================================


class TestOnFilterDialogStart:
    async def test_clears_stale_dialog_data_when_reopened_without_filters(self):
        from telegram_bot.dialogs.filter_dialog import on_filter_dialog_start

        manager = MagicMock()
        manager.dialog_data = {
            "city": "Бургас",
            "rooms": "3",
            "budget": "mid",
        }
        widget_data = {
            "r_city": "Бургас",
            "r_rooms": "3",
            "r_budget": "mid",
        }

        radio_widgets = {
            radio_id: AsyncMock(set_checked=AsyncMock())
            for radio_id in (
                "r_city",
                "r_rooms",
                "r_budget",
                "r_view",
                "r_area",
                "r_floor",
                "r_complex",
                "r_furnished",
                "r_promotion",
            )
        }
        manager.current_context = MagicMock(return_value=SimpleNamespace(widget_data=widget_data))
        manager.find = MagicMock(side_effect=lambda radio_id: radio_widgets[radio_id])

        await on_filter_dialog_start({"filters": {}}, manager)

        assert manager.dialog_data == {}
        assert widget_data == {}
        for widget in radio_widgets.values():
            widget.set_checked.assert_not_awaited()

    async def test_populates_dialog_data_from_existing_filters(self):
        from telegram_bot.dialogs.filter_dialog import on_filter_dialog_start

        manager = MagicMock()
        manager.dialog_data = {"city": "stale"}
        widget_data = {
            "r_city": "stale",
            "r_rooms": "stale",
            "r_budget": "stale",
        }

        radio_widgets = {
            radio_id: AsyncMock(set_checked=AsyncMock())
            for radio_id in (
                "r_city",
                "r_rooms",
                "r_budget",
                "r_view",
                "r_area",
                "r_floor",
                "r_complex",
                "r_furnished",
                "r_promotion",
            )
        }
        manager.current_context = MagicMock(return_value=SimpleNamespace(widget_data=widget_data))
        manager.find = MagicMock(side_effect=lambda radio_id: radio_widgets[radio_id])

        await on_filter_dialog_start({"filters": {"city": "Несебр", "rooms": 2}}, manager)

        assert manager.dialog_data["city"] == "Несебр"
        assert manager.dialog_data["rooms"] == "2"
        assert widget_data == {}
        radio_widgets["r_city"].set_checked.assert_awaited_once_with("Несебр")
        radio_widgets["r_rooms"].set_checked.assert_awaited_once_with("2")
        radio_widgets["r_budget"].set_checked.assert_not_awaited()


# ============================================================
# Getter tests — all use "any" sentinel
# ============================================================


class TestFilterWindowGetters:
    async def test_get_city_data_returns_options(self):
        from telegram_bot.dialogs.filter_dialog import get_city_data

        manager = SimpleNamespace(dialog_data={"city": "Варна"})
        result = await get_city_data(dialog_manager=manager)
        assert "city_options" in result
        labels = [label for label, _ in result["city_options"]]
        assert any("Любой" in label for label in labels)

    async def test_get_budget_data_returns_options(self):
        from telegram_bot.dialogs.filter_dialog import get_budget_data

        manager = SimpleNamespace(dialog_data={})
        result = await get_budget_data(dialog_manager=manager)
        assert "budget_options" in result
        assert len(result["budget_options"]) >= 5

    async def test_get_rooms_data_returns_options(self):
        from telegram_bot.dialogs.filter_dialog import get_rooms_data

        manager = SimpleNamespace(dialog_data={})
        result = await get_rooms_data(dialog_manager=manager)
        assert "rooms_options" in result
        assert len(result["rooms_options"]) > 0

    async def test_all_getters_use_any_sentinel_not_empty_string(self):
        """Verify "Любой"/"Любое" options use 'any' item_id, not empty string."""
        from telegram_bot.dialogs.filter_dialog import (
            get_area_data,
            get_budget_data,
            get_city_data,
            get_floor_data,
            get_furnished_data,
            get_promotion_data,
            get_rooms_data,
            get_view_data,
        )

        manager = SimpleNamespace(dialog_data={})
        getters = [
            ("city_options", get_city_data),
            ("rooms_options", get_rooms_data),
            ("budget_options", get_budget_data),
            ("view_options", get_view_data),
            ("area_options", get_area_data),
            ("floor_options", get_floor_data),
            ("furnished_options", get_furnished_data),
            ("promotion_options", get_promotion_data),
        ]
        for key, getter in getters:
            result = await getter(dialog_manager=manager)
            options = result[key]
            first_label, first_value = options[0]
            assert "Люб" in first_label, f"{key}: first option should be Любой/Любое"
            assert first_value == "any", f"{key}: sentinel should be 'any', got '{first_value}'"


# ============================================================
# Radio handler — item_id="any" clears filter, valid stores coerced
# ============================================================


class TestRadioHandlerAnySentinel:
    async def test_any_clears_filter_from_dialog_data(self):
        from telegram_bot.dialogs.filter_dialog import _make_radio_handler

        handler = _make_radio_handler("city")
        manager = AsyncMock()
        manager.dialog_data = {"city": "Несебр"}
        manager.switch_to = AsyncMock()

        await handler(MagicMock(), MagicMock(), manager, "any")

        assert "city" not in manager.dialog_data
        manager.switch_to.assert_awaited_once_with(FilterSG.hub)

    async def test_any_clears_translated_key_too(self):
        from telegram_bot.dialogs.filter_dialog import _make_radio_handler

        handler = _make_radio_handler("complex")
        manager = AsyncMock()
        manager.dialog_data = {"complex": "Fort Noks", "complex_name": "Fort Noks"}
        manager.switch_to = AsyncMock()

        await handler(MagicMock(), MagicMock(), manager, "any")

        assert "complex" not in manager.dialog_data
        assert "complex_name" not in manager.dialog_data

    async def test_valid_value_stores_raw_item_id(self):
        from telegram_bot.dialogs.filter_dialog import _make_radio_handler

        handler = _make_radio_handler("rooms")
        manager = AsyncMock()
        manager.dialog_data = {}
        manager.switch_to = AsyncMock()

        await handler(MagicMock(), MagicMock(), manager, "3")

        assert manager.dialog_data["rooms"] == "3"

    async def test_valid_city_stores_string(self):
        from telegram_bot.dialogs.filter_dialog import _make_radio_handler

        handler = _make_radio_handler("city")
        manager = AsyncMock()
        manager.dialog_data = {}
        manager.switch_to = AsyncMock()

        await handler(MagicMock(), MagicMock(), manager, "Бургас")

        assert manager.dialog_data["city"] == "Бургас"


# ============================================================
# _filters_to_dialog_data — reverse mapping
# ============================================================


class TestFiltersToDialogData:
    def test_reverse_maps_complex_name(self):
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        result = _filters_to_dialog_data({"complex_name": "Fort Noks"})
        assert result["complex"] == "Fort Noks"

    def test_reverse_maps_view_tags(self):
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        result = _filters_to_dialog_data({"view_tags": ["sea"]})
        assert result["view"] == "sea"

    def test_reverse_maps_price_eur_to_budget(self):
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        result = _filters_to_dialog_data({"price_eur": {"gte": 50_000, "lte": 100_000}})
        assert result["budget"] == "mid"

    def test_reverse_maps_area_m2_to_string_key(self):
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        result = _filters_to_dialog_data({"area_m2": {"gte": 60, "lte": 80}})
        assert result["area"] == "large"

    def test_reverse_maps_floor_to_string_key(self):
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        result = _filters_to_dialog_data({"floor": {"gte": 4, "lte": 5}})
        assert result["floor"] == "high"

    def test_reverse_maps_rooms_to_string(self):
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        result = _filters_to_dialog_data({"rooms": 3})
        assert result["rooms"] == "3"

    def test_reverse_maps_furnished_to_string(self):
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        result = _filters_to_dialog_data({"is_furnished": True})
        assert result["furnished"] == "true"

    def test_empty_filters(self):
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        assert _filters_to_dialog_data({}) == {}

    def test_reverse_maps_rooms_list_to_studio(self):
        """Funnel sends rooms=[0, 1] for studio — should map to '1' for Radio."""
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        result = _filters_to_dialog_data({"rooms": [0, 1]})
        assert result["rooms"] == "1"

    def test_reverse_maps_promotion(self):
        from telegram_bot.dialogs.filter_dialog import _filters_to_dialog_data

        result = _filters_to_dialog_data({"is_promotion": True})
        assert result["promotion"] == "true"


# ============================================================
# Hub displays all active filters
# ============================================================


class TestHubDisplaysActiveFilters:
    async def test_hub_shows_only_active_filters(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        manager = SimpleNamespace(
            dialog_data={"city": "Варна", "view": "sea", "area": "large"},
            middleware_data={"apartments_service": None},
        )
        result = await get_hub_data(dialog_manager=manager)
        text = result["active_filters"]
        assert "Варна" in text
        assert "Море" in text
        assert "60–80 m²" in text
        # Unset filters should NOT appear
        assert "Комнаты" not in text
        assert "Бюджет" not in text
        assert "Мебель" not in text

    async def test_hub_shows_all_set_filters(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        manager = SimpleNamespace(
            dialog_data={
                "city": "Бургас",
                "rooms": "2",
                "budget": "mid",
                "view": "pool",
                "area": "xlarge",
                "floor": "high",
                "complex": "Crown Fort Club",
                "furnished": "true",
                "promotion": "true",
            },
            middleware_data={"apartments_service": None},
        )
        result = await get_hub_data(dialog_manager=manager)
        text = result["active_filters"]
        assert "Бургас" in text
        assert "1-спальня" in text
        assert "50 000" in text
        assert "Бассейн" in text
        assert "80–120 m²" in text
        assert "4-5 этаж" in text
        assert "Crown Fort Club" in text
        assert "Мебель: Да" in text
        assert "акции" in text.lower()

    async def test_hub_empty_shows_no_filters(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        manager = SimpleNamespace(
            dialog_data={},
            middleware_data={"apartments_service": None},
        )
        result = await get_hub_data(dialog_manager=manager)
        assert result["active_filters"] == "Фильтры не заданы"

    async def test_hub_ignores_stale_none_strings(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        manager = SimpleNamespace(
            dialog_data={
                "city": "None",
                "rooms": "None",
                "budget": "None",
                "view": "None",
                "area": "None",
                "floor": "None",
                "complex": "None",
                "furnished": "None",
            },
            middleware_data={"apartments_service": None},
        )
        result = await get_hub_data(dialog_manager=manager)
        assert result["active_filters"] == "Фильтры не заданы"
