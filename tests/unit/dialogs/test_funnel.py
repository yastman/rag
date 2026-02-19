"""Tests for BANT funnel dialog."""

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
    assert FunnelSG.property_type in states
    assert FunnelSG.budget in states
    assert FunnelSG.timeline in states
    assert FunnelSG.results in states


@pytest.mark.asyncio
async def test_timeline_selection_schedules_background_persist_and_switches(monkeypatch):
    spawn_mock = MagicMock()
    monkeypatch.setattr(funnel_module, "_spawn_persist_funnel_lead_score", spawn_mock)

    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=12345),
        message=SimpleNamespace(chat=SimpleNamespace(id=777)),
    )
    manager = SimpleNamespace(
        dialog_data={"property_type": "apartment", "budget": "mid"},
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

    await funnel_module.on_timeline_selected(
        callback=callback,
        widget=SimpleNamespace(),
        manager=manager,
        item_id="asap",
    )

    spawn_mock.assert_called_once()
    assert spawn_mock.call_args.kwargs["telegram_user_id"] == 12345
    assert spawn_mock.call_args.kwargs["property_type"] == "apartment"
    assert spawn_mock.call_args.kwargs["budget"] == "mid"
    assert spawn_mock.call_args.kwargs["timeline"] == "asap"
    manager.switch_to.assert_awaited_once_with(FunnelSG.results)


@pytest.mark.asyncio
async def test_timeline_selection_fail_soft_when_schedule_raises(monkeypatch):
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

    await funnel_module.on_timeline_selected(
        callback=callback,
        widget=SimpleNamespace(),
        manager=manager,
        item_id="3months",
    )

    manager.switch_to.assert_awaited_once_with(FunnelSG.results)
