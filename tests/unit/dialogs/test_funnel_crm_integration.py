"""Tests for funnel → CRM integration (lead scoring payload, FSM state persistence)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import telegram_bot.dialogs.funnel as funnel_module
from telegram_bot.dialogs.states import FunnelSG


async def test_summary_search_calls_lead_scoring(monkeypatch):
    """on_summary_search calls _spawn_persist_funnel_lead_score with correct kwargs."""
    spawn_calls: list[dict] = []

    def fake_spawn(**kwargs: Any) -> None:
        spawn_calls.append(kwargs)

    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", fake_spawn)

    callback = MagicMock()
    callback.from_user = MagicMock(id=42)
    callback.message = MagicMock(chat=MagicMock(id=100))

    manager = SimpleNamespace(
        dialog_data={"city": "Элените", "property_type": "2bed", "budget": "high"},
        middleware_data={
            "user_service": MagicMock(),
            "pg_pool": MagicMock(),
            "lead_scoring_store": MagicMock(),
            "kommo_client": MagicMock(),
            "hot_lead_notifier": MagicMock(),
            "bot_config": MagicMock(),
        },
        switch_to=AsyncMock(),
        done=AsyncMock(),
    )

    await funnel_module.on_summary_search(callback, MagicMock(), manager)

    assert len(spawn_calls) == 1
    assert spawn_calls[0]["telegram_user_id"] == 42
    assert spawn_calls[0]["property_type"] == "2bed"
    assert spawn_calls[0]["budget"] == "high"


async def test_summary_search_stores_filters_in_fsm(monkeypatch):
    """on_summary_search stores apartment_filters in FSM state."""
    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", MagicMock())

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
    state_mock.set_state = AsyncMock()

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

    # Filters now cached in dialog_data for results window (#935), not directly in FSM
    assert "_search_filters" in manager.dialog_data
    assert "_search_results" in manager.dialog_data
    assert manager.dialog_data.get("city") == "Элените"


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
