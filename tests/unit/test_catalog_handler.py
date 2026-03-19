"""Tests for dialog-owned catalog controls and legacy path removal."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_state(data: dict) -> MagicMock:
    state = MagicMock()
    state.get_data = AsyncMock(return_value=data)
    state.update_data = AsyncMock()
    return state


def _make_callback() -> MagicMock:
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.from_user = MagicMock(id=123)
    return callback


def test_catalog_browsing_state_is_removed() -> None:
    from telegram_bot.dialogs import states

    assert not hasattr(states, "CatalogBrowsingSG")


def test_bot_no_longer_registers_catalog_reply_keyboard_path() -> None:
    source = Path("telegram_bot/bot.py").read_text()
    assert "CatalogBrowsingSG.browsing" not in source
    assert "include_router(catalog_router)" not in source


@pytest.mark.asyncio
async def test_catalog_more_loads_next_page_and_updates_runtime() -> None:
    from telegram_bot.dialogs.catalog import on_catalog_more

    state = _make_state(
        {
            "catalog_runtime": {
                "shown_count": 10,
                "total": 25,
                "next_offset": 80000.0,
                "shown_item_ids": ["apt-1"],
                "filters": {"rooms": 2},
                "view_mode": "list",
            }
        }
    )
    svc = MagicMock()
    svc.scroll_with_filters = AsyncMock(
        return_value=([{"id": "apt-2"}] * 10, 25, 90000.0, ["apt-2"])
    )
    property_bot = MagicMock()
    property_bot._apartments_service = svc
    manager = AsyncMock()
    manager.middleware_data = {"state": state, "property_bot": property_bot}

    await on_catalog_more(_make_callback(), MagicMock(), manager)

    svc.scroll_with_filters.assert_awaited_once()
    update_kwargs = state.update_data.call_args.kwargs
    assert update_kwargs["catalog_runtime"]["shown_count"] == 20


@pytest.mark.asyncio
async def test_catalog_more_uses_callback_user_id_for_cards() -> None:
    from telegram_bot.dialogs.catalog import on_catalog_more

    state = _make_state(
        {
            "catalog_runtime": {
                "shown_count": 0,
                "total": 1,
                "next_offset": 1.0,
                "shown_item_ids": [],
                "filters": {},
                "view_mode": "cards",
            }
        }
    )
    svc = MagicMock()
    svc.scroll_with_filters = AsyncMock(return_value=([{"id": "apt-2"}], 1, None, ["apt-2"]))
    property_bot = MagicMock()
    property_bot._apartments_service = svc
    property_bot._send_property_card = AsyncMock()
    manager = AsyncMock()
    manager.middleware_data = {"state": state, "property_bot": property_bot}
    callback = _make_callback()
    callback.message.from_user = MagicMock(id=999999)

    await on_catalog_more(callback, MagicMock(), manager)

    property_bot._send_property_card.assert_awaited_once_with(
        callback.message, {"id": "apt-2"}, 123
    )


@pytest.mark.asyncio
async def test_catalog_filters_starts_filter_dialog() -> None:
    from telegram_bot.dialogs.catalog import on_catalog_filters
    from telegram_bot.dialogs.states import FilterSG

    state = _make_state({"catalog_runtime": {"filters": {"city": "Варна"}}})
    manager = AsyncMock()
    manager.middleware_data = {"state": state}

    await on_catalog_filters(_make_callback(), MagicMock(), manager)

    manager.start.assert_awaited_once_with(FilterSG.hub, data={"filters": {"city": "Варна"}})


@pytest.mark.asyncio
async def test_catalog_bookmarks_delegates_to_property_bot() -> None:
    from telegram_bot.dialogs.catalog import on_catalog_bookmarks

    state = _make_state({})
    property_bot = MagicMock()
    property_bot._handle_bookmarks = AsyncMock()
    manager = AsyncMock()
    manager.middleware_data = {"state": state, "property_bot": property_bot}
    callback = _make_callback()

    await on_catalog_bookmarks(callback, MagicMock(), manager)

    property_bot._handle_bookmarks.assert_awaited_once()
    passed_message = property_bot._handle_bookmarks.await_args.args[0]
    assert passed_message.from_user is callback.from_user


@pytest.mark.asyncio
async def test_catalog_viewing_delegates_to_existing_handler() -> None:
    from telegram_bot.dialogs.catalog import on_catalog_viewing

    state = _make_state({})
    property_bot = MagicMock()
    property_bot._handle_viewing = AsyncMock()
    manager = AsyncMock()
    manager.middleware_data = {"state": state, "property_bot": property_bot}
    callback = _make_callback()

    await on_catalog_viewing(callback, MagicMock(), manager)

    property_bot._handle_viewing.assert_awaited_once()


@pytest.mark.asyncio
async def test_catalog_manager_delegates_to_existing_handler() -> None:
    from telegram_bot.dialogs.catalog import on_catalog_manager

    state = _make_state({})
    property_bot = MagicMock()
    property_bot._handle_manager = AsyncMock()
    manager = AsyncMock()
    manager.middleware_data = {"state": state, "property_bot": property_bot, "i18n": None}
    callback = _make_callback()

    await on_catalog_manager(callback, MagicMock(), manager)

    property_bot._handle_manager.assert_awaited_once()
    passed_message = property_bot._handle_manager.await_args.args[0]
    assert passed_message.from_user is callback.from_user
