"""Tests for property search funnel dialog (#628)."""

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
    assert FunnelSG.location in states
    assert FunnelSG.property_type in states
    assert FunnelSG.budget in states
    assert FunnelSG.refine_or_show in states
    assert FunnelSG.floor in states
    assert FunnelSG.view in states
    assert FunnelSG.results in states


@pytest.mark.asyncio
async def test_show_results_schedules_background_persist(monkeypatch):
    spawn_mock = MagicMock()
    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", spawn_mock)

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(chat=SimpleNamespace(id=777)),
    )
    manager = SimpleNamespace(
        dialog_data={"location": "sunny_beach", "property_type": "2bed", "budget": "mid"},
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

    await funnel_module.on_refine_or_show_selected(
        callback=callback,
        widget=SimpleNamespace(),
        manager=manager,
        item_id="show",
    )

    spawn_mock.assert_called_once()
    assert spawn_mock.call_args.kwargs["telegram_user_id"] == 12345
    assert spawn_mock.call_args.kwargs["property_type"] == "2bed"
    assert spawn_mock.call_args.kwargs["budget"] == "mid"
    assert spawn_mock.call_args.kwargs["timeline"] == "show"
    assert manager.dialog_data["refine_or_show"] == "show"
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


@pytest.mark.asyncio
async def test_show_results_fail_soft(monkeypatch):
    def _raise_on_schedule(**kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", _raise_on_schedule)

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        message=SimpleNamespace(chat=SimpleNamespace(id=2)),
    )
    manager = SimpleNamespace(
        dialog_data={},
        middleware_data={},
        switch_to=AsyncMock(),
    )

    await funnel_module.on_refine_or_show_selected(
        callback=callback,
        widget=SimpleNamespace(),
        manager=manager,
        item_id="show",
    )

    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


@pytest.mark.asyncio
async def test_refine_path_switches_to_floor(monkeypatch):
    callback = SimpleNamespace(from_user=SimpleNamespace(id=1), message=None)
    manager = SimpleNamespace(
        dialog_data={},
        middleware_data={},
        switch_to=AsyncMock(),
    )

    await funnel_module.on_refine_or_show_selected(
        callback=callback,
        widget=SimpleNamespace(),
        manager=manager,
        item_id="refine",
    )

    assert manager.dialog_data["refine_or_show"] == "refine"
    manager.switch_to.assert_awaited_once_with(FunnelSG.floor)


@pytest.mark.asyncio
async def test_view_selected_schedules_persist_and_switches(monkeypatch):
    spawn_mock = MagicMock()
    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", spawn_mock)

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=99),
        message=SimpleNamespace(chat=SimpleNamespace(id=111)),
    )
    manager = SimpleNamespace(
        dialog_data={
            "property_type": "studio",
            "budget": "low",
            "floor": "mid",
            "refine_or_show": "refine",
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

    await funnel_module.on_view_selected(
        callback=callback,
        widget=SimpleNamespace(),
        manager=manager,
        item_id="sea",
    )

    assert manager.dialog_data["view"] == "sea"
    spawn_mock.assert_called_once()
    assert spawn_mock.call_args.kwargs["telegram_user_id"] == 99
    assert spawn_mock.call_args.kwargs["timeline"] == "refine"
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)
