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

        # filter_dialog.windows is a dict: State → Window
        # State.state has format "FilterSG:hub"
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


# ============================================================
# Hub getter — get_hub_data
# ============================================================


class TestGetHubData:
    async def test_returns_city_options(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        manager = SimpleNamespace(
            dialog_data={"city": "Солнечный берег"},
            middleware_data={"apartments_service": None},
        )
        result = await get_hub_data(dialog_manager=manager)
        assert "city_options" in result

    async def test_returns_budget_options(self):
        from telegram_bot.dialogs.filter_dialog import get_hub_data

        manager = SimpleNamespace(
            dialog_data={},
            middleware_data={"apartments_service": None},
        )
        result = await get_hub_data(dialog_manager=manager)
        assert "budget_options" in result

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


# ============================================================
# on_apply — saves filters to FSMContext and closes dialog
# ============================================================


class TestOnApply:
    async def test_saves_filters_to_fsm(self):
        from telegram_bot.dialogs.filter_dialog import on_apply

        state = AsyncMock()
        state.update_data = AsyncMock()

        manager = AsyncMock()
        manager.dialog_data = {"city": "Несебр", "budget": "mid"}
        manager.middleware_data = {"state": state}
        manager.done = AsyncMock()

        await on_apply(MagicMock(), MagicMock(), manager)

        state.update_data.assert_awaited_once()
        call_kwargs = state.update_data.call_args[1]
        filters = call_kwargs["apartment_filters"]
        assert filters["city"] == "Несебр"
        assert "price_eur" in filters
        assert "budget" not in filters

    async def test_calls_manager_done(self):
        from telegram_bot.dialogs.filter_dialog import on_apply

        state = AsyncMock()
        state.update_data = AsyncMock()

        manager = AsyncMock()
        manager.dialog_data = {}
        manager.middleware_data = {"state": state}
        manager.done = AsyncMock()

        await on_apply(MagicMock(), MagicMock(), manager)
        manager.done.assert_awaited_once()

    async def test_resets_pagination_state(self):
        from telegram_bot.dialogs.filter_dialog import on_apply

        state = AsyncMock()
        state.update_data = AsyncMock()

        manager = AsyncMock()
        manager.dialog_data = {"city": "Варна"}
        manager.middleware_data = {"state": state}
        manager.done = AsyncMock()

        await on_apply(MagicMock(), MagicMock(), manager)

        call_kwargs = state.update_data.call_args[1]
        assert call_kwargs.get("apartment_offset") == 0


# ============================================================
# on_reset — clears dialog_data filters
# ============================================================


class TestOnReset:
    async def test_clears_all_filter_fields(self):
        from telegram_bot.dialogs.filter_dialog import on_reset

        manager = AsyncMock()
        manager.dialog_data = {"city": "Варна", "budget": "mid", "rooms": 2}

        await on_reset(MagicMock(), MagicMock(), manager)

        for field in ("city", "budget", "rooms"):
            assert manager.dialog_data.get(field) is None or field not in manager.dialog_data


# ============================================================
# Getter for individual filter windows
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
        # 5 tiers + optional "Любой" clear option
        assert len(result["budget_options"]) >= 5

    async def test_get_rooms_data_returns_options(self):
        from telegram_bot.dialogs.filter_dialog import get_rooms_data

        manager = SimpleNamespace(dialog_data={})
        result = await get_rooms_data(dialog_manager=manager)
        assert "rooms_options" in result
        assert len(result["rooms_options"]) > 0
