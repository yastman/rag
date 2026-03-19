"""Tests for the dialog-owned catalog shell."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.states import CatalogSG, ClientMenuSG, FilterSG


def test_catalog_dialog_has_results_window() -> None:
    from telegram_bot.dialogs.catalog import catalog_dialog

    assert CatalogSG.results in catalog_dialog.windows


def test_catalog_results_window_has_expected_control_buttons() -> None:
    from telegram_bot.dialogs.catalog import catalog_dialog

    window = catalog_dialog.windows[CatalogSG.results]
    widget_ids = {getattr(widget, "widget_id", None) for widget in window.keyboard.buttons}
    assert "catalog_more" in widget_ids
    assert "catalog_filters" in widget_ids
    assert "catalog_home" in widget_ids


@pytest.mark.asyncio
async def test_catalog_home_uses_reset_stack_to_client_root() -> None:
    from aiogram_dialog import StartMode

    from telegram_bot.dialogs.catalog import on_catalog_home

    manager = AsyncMock()
    await on_catalog_home(MagicMock(), MagicMock(), manager)

    manager.start.assert_awaited_once_with(ClientMenuSG.main, mode=StartMode.RESET_STACK)


@pytest.mark.asyncio
async def test_catalog_filters_starts_filter_dialog_with_current_filters() -> None:
    from telegram_bot.dialogs.catalog import on_catalog_filters

    state = AsyncMock()
    state.get_data.return_value = {"catalog_runtime": {"filters": {"city": "Варна"}}}
    manager = AsyncMock()
    manager.middleware_data = {"state": state}

    await on_catalog_filters(MagicMock(), MagicMock(), manager)

    manager.start.assert_awaited_once_with(FilterSG.hub, data={"filters": {"city": "Варна"}})
