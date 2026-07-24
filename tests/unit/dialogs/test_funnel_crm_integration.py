"""Tests for funnel summary search FSM state persistence and display details."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import telegram_bot.dialogs.funnel as funnel_module
from telegram_bot.dialogs.states import FunnelSG


async def test_summary_search_stores_filters_in_fsm(monkeypatch):
    """on_summary_search stores catalog_runtime in FSM state."""

    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(
        return_value=(
            [
                {
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
            ],
            1,
            None,
            ["a1"],
        )
    )
    mock_bot = MagicMock()
    mock_bot._send_property_card = AsyncMock()
    mock_bot._apartments_service = mock_svc

    state_mock = MagicMock()
    state_mock.update_data = AsyncMock()
    state_mock.get_data = AsyncMock(return_value={})

    callback = MagicMock()
    callback.from_user = MagicMock(id=1)
    callback.message = MagicMock(chat=MagicMock(id=2))
    callback.message.answer = AsyncMock()

    manager = MagicMock()
    manager.dialog_data = {"city": "Элените", "property_type": "1bed", "budget": "low"}
    manager.middleware_data = {
        "apartments_service": mock_svc,
        "property_bot": mock_bot,
        "state": state_mock,
    }
    manager.done = AsyncMock()
    manager.switch_to = AsyncMock()

    await funnel_module.on_summary_search(callback, MagicMock(), manager)

    assert state_mock.update_data.await_count >= 1
    call_kwargs = next(
        kwargs
        for _, kwargs in state_mock.update_data.await_args_list
        if "catalog_runtime" in kwargs
    )
    assert "catalog_runtime" in call_kwargs
    assert call_kwargs["catalog_runtime"]["filters"]["city"] == "Элените"
    assert call_kwargs["catalog_runtime"]["origin_context"]["funnel_data"]["city"] == "Элените"


async def test_zero_suggestion_rm_section():
    """rm_section removes section and resets scroll."""
    manager = SimpleNamespace(
        dialog_data={"section": "D-1", "scroll_start_from": 1.0, "scroll_seen_ids": ["x"]},
        switch_to=AsyncMock(),
    )
    await funnel_module.on_zero_suggestion_selected(
        MagicMock(), SimpleNamespace(), manager, "rm_section"
    )
    assert "section" not in manager.dialog_data
    assert manager.dialog_data.get("scroll_start_from") is None
    manager.switch_to.assert_awaited_once_with(FunnelSG.summary)


async def test_summary_shows_section():
    """Summary displays selected section."""
    result = await funnel_module.get_summary_data(
        dialog_manager=SimpleNamespace(
            dialog_data={
                "city": "any",
                "property_type": "any",
                "budget": "any",
                "section": "D-1",
            },
            middleware_data={},
        ),
    )
    assert "Секция: D-1" in result["summary_text"]
