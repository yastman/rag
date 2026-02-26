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


@pytest.mark.asyncio
async def test_location_options_has_exactly_3_cities_plus_any():
    """Funnel must only offer cities that exist in data: Sunny Beach, Elenite, Nesebar + Any."""
    result = await funnel_module.get_location_options()
    items = result["items"]
    keys = [key for _, key in items]
    # Only real cities + any
    assert "sunny_beach" in keys
    assert "elenite" in keys
    assert "nessebar" in keys
    assert "any" in keys
    # Removed phantom cities
    assert "sveti_vlas" not in keys
    assert "ravda" not in keys
    assert "burgas" not in keys
    assert "pomorie" not in keys
    assert "sozopol" not in keys
    assert "primorsko" not in keys
    assert "bansko" not in keys
    assert "sofia" not in keys
    # Total: 3 real + 1 any = 4
    assert len(items) == 4


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
async def test_get_results_data_calls_apartments_service():
    mock_search = AsyncMock(
        return_value=[
            {
                "id": "p1",
                "score": 0.95,
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
    )
    mock_aembed = AsyncMock(return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}))

    mock_svc = MagicMock()
    mock_svc.search = mock_search
    mock_embeddings = MagicMock()
    mock_embeddings.aembed_hybrid = mock_aembed

    manager = SimpleNamespace(
        dialog_data={"location": "sunny_beach", "property_type": "studio", "budget": "low"},
        middleware_data={
            "apartments_service": mock_svc,
            "hybrid_embeddings": mock_embeddings,
        },
    )

    result = await funnel_module.get_results_data(manager)

    mock_embeddings.aembed_hybrid.assert_awaited_once_with("Sunny Beach студия")
    mock_svc.search.assert_awaited_once()
    assert "Sunrise" in result["results_text"]
    assert "Sunny Beach" in result["results_text"]
    assert "sunny_beach" not in result["results_text"]


@pytest.mark.asyncio
async def test_get_results_data_any_any_uses_fallback_query():
    mock_search = AsyncMock(return_value=[])
    mock_aembed = AsyncMock(return_value=([0.1] * 1024, {"indices": [], "values": []}))

    mock_svc = MagicMock()
    mock_svc.search = mock_search
    mock_embeddings = MagicMock()
    mock_embeddings.aembed_hybrid = mock_aembed

    manager = SimpleNamespace(
        dialog_data={"location": "any", "property_type": "any", "budget": "any"},
        middleware_data={
            "apartments_service": mock_svc,
            "hybrid_embeddings": mock_embeddings,
        },
    )

    await funnel_module.get_results_data(manager)

    mock_embeddings.aembed_hybrid.assert_awaited_once_with("апартаменты в Болгарии")
    mock_svc.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_results_data_fallback_without_service():
    manager = SimpleNamespace(
        dialog_data={},
        middleware_data={},
    )

    result = await funnel_module.get_results_data(manager)

    assert "не нашли" in result["results_text"].lower()


@pytest.mark.asyncio
async def test_get_results_data_uses_property_bot_fallback():
    mock_search = AsyncMock(return_value=[])
    mock_aembed = AsyncMock(return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}))

    mock_svc = MagicMock()
    mock_svc.search = mock_search
    mock_embeddings = MagicMock()
    mock_embeddings.aembed_hybrid = mock_aembed

    mock_property_bot = MagicMock()
    mock_property_bot._apartments_service = mock_svc
    mock_property_bot._embeddings = mock_embeddings

    manager = SimpleNamespace(
        dialog_data={"location": "sunny_beach", "property_type": "studio", "budget": "low"},
        middleware_data={"property_bot": mock_property_bot},
    )

    await funnel_module.get_results_data(manager)

    mock_embeddings.aembed_hybrid.assert_awaited_once()
    mock_svc.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_location_selected_saves_and_switches():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())

    await funnel_module.on_location_selected(MagicMock(), SimpleNamespace(), manager, "sunny_beach")

    assert manager.dialog_data["location"] == "sunny_beach"
    manager.switch_to.assert_awaited_once_with(FunnelSG.property_type)


@pytest.mark.asyncio
async def test_property_type_selected_saves_and_switches():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())

    await funnel_module.on_property_type_selected(MagicMock(), SimpleNamespace(), manager, "studio")

    assert manager.dialog_data["property_type"] == "studio"
    manager.switch_to.assert_awaited_once_with(FunnelSG.budget)


@pytest.mark.asyncio
async def test_budget_selected_saves_and_switches():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())

    await funnel_module.on_budget_selected(MagicMock(), SimpleNamespace(), manager, "mid")

    assert manager.dialog_data["budget"] == "mid"
    manager.switch_to.assert_awaited_once_with(FunnelSG.refine_or_show)


@pytest.mark.asyncio
async def test_floor_selected_saves_and_switches():
    manager = SimpleNamespace(dialog_data={}, switch_to=AsyncMock())

    await funnel_module.on_floor_selected(MagicMock(), SimpleNamespace(), manager, "mid")

    assert manager.dialog_data["floor"] == "mid"
    manager.switch_to.assert_awaited_once_with(FunnelSG.view)


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
