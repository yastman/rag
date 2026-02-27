"""Tests for funnel filter building and results getter (#660)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.funnel import build_funnel_filters


# --- build_funnel_filters ---


def test_rooms_studio():
    filters = build_funnel_filters(rooms="studio", budget="any")
    assert filters.get("rooms") == [0, 1]
    assert "price_eur" not in filters


def test_rooms_2_bedrooms():
    filters = build_funnel_filters(rooms="2bed", budget="any")
    assert filters.get("rooms") == 3


def test_budget_mid_50_100():
    filters = build_funnel_filters(rooms="any", budget="mid")
    assert "price_eur" in filters
    assert filters["price_eur"] == {"gte": 50000, "lte": 100000}


def test_budget_any_no_filter():
    filters = build_funnel_filters(rooms="any", budget="any")
    assert "rooms" not in filters
    assert "price_eur" not in filters


def test_with_view_sea():
    filters = build_funnel_filters(rooms="any", budget="any", view="sea")
    assert "view_tags" in filters
    assert filters["view_tags"] == ["sea"]


def test_view_any_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", view="any")
    assert "view_tags" not in filters


def test_with_floor_mid():
    filters = build_funnel_filters(rooms="any", budget="any", floor="mid")
    assert "floor" in filters
    assert filters["floor"] == {"gte": 2, "lte": 3}


def test_floor_any_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", floor="any")
    assert "floor" not in filters


def test_floor_top():
    filters = build_funnel_filters(rooms="any", budget="any", floor="top")
    assert filters["floor"] == {"gte": 6}


def test_budget_luxury():
    filters = build_funnel_filters(rooms="any", budget="luxury")
    assert filters["price_eur"] == {"gte": 200000}


def test_complex_name_filter():
    filters = build_funnel_filters(rooms="any", budget="any", complex_name="Sunrise")
    assert filters["complex_name"] == "Sunrise"


def test_city_filter_maps_location_to_city():
    filters = build_funnel_filters(rooms="any", budget="any", city="sunny_beach")
    assert filters["city"] == "Sunny Beach"


def test_city_any_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", city="any")
    assert "city" not in filters


# --- get_results_data integration (mocked svc) ---


@pytest.mark.asyncio
async def test_get_results_data_returns_cards():
    """get_results_data calls search with embeddings and formats cards."""
    from telegram_bot.dialogs.funnel import get_results_data

    mock_svc = MagicMock()
    mock_svc.search = AsyncMock(
        return_value=[
            {
                "id": "apt-1",
                "payload": {
                    "complex_name": "Sunrise Complex",
                    "rooms": 1,
                    "floor": 2,
                    "area_m2": 42.0,
                    "view_primary": "Море",
                    "price_eur": 48500,
                },
            }
        ],
    )

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid = AsyncMock(
        return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]})
    )

    manager = SimpleNamespace(
        dialog_data={"property_type": "studio", "budget": "low", "location": "sunny_beach"},
        middleware_data={"apartments_service": mock_svc, "hybrid_embeddings": mock_embeddings},
    )

    result = await get_results_data(dialog_manager=manager)
    assert result["title"] == "Подобрали для вас:"
    assert "Sunrise Complex" in result["results_text"]
    mock_svc.search.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_results_data_no_results():
    """get_results_data returns empty message when no apartments match."""
    from telegram_bot.dialogs.funnel import get_results_data

    mock_svc = MagicMock()
    mock_svc.search = AsyncMock(return_value=[])

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid = AsyncMock(
        return_value=([0.1] * 1024, {"indices": [], "values": []})
    )

    manager = SimpleNamespace(
        dialog_data={"property_type": "3bed", "budget": "luxury"},
        middleware_data={"apartments_service": mock_svc, "hybrid_embeddings": mock_embeddings},
    )

    result = await get_results_data(dialog_manager=manager)
    assert "ничего не найдено" in result["results_text"]


@pytest.mark.asyncio
async def test_get_results_data_no_service():
    """get_results_data returns placeholder when service unavailable."""
    from telegram_bot.dialogs.funnel import get_results_data

    manager = SimpleNamespace(
        dialog_data={"property_type": "any", "budget": "any"},
        middleware_data={},
    )

    result = await get_results_data(dialog_manager=manager)
    assert result["results_text"]  # non-empty fallback
    assert result["btn_back"] == "Назад"


@pytest.mark.asyncio
async def test_get_results_data_malformed_payload():
    """get_results_data must not crash when search returns items without payload key."""
    from telegram_bot.dialogs.funnel import get_results_data

    mock_svc = MagicMock()
    mock_svc.search = AsyncMock(
        return_value=[
            {"id": "apt-bad"},  # missing "payload" key
        ],
    )

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid = AsyncMock(
        return_value=([0.1] * 16, {"indices": [], "values": []})
    )

    manager = SimpleNamespace(
        dialog_data={"property_type": "any", "budget": "any"},
        middleware_data={"apartments_service": mock_svc, "hybrid_embeddings": mock_embeddings},
    )

    result = await get_results_data(dialog_manager=manager)
    # Must not crash — falls through to no_results_text via exception handler
    assert result["results_text"]
