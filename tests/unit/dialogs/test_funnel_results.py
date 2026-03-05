"""Tests for funnel filter building and results getter (#697)."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.dialogs.funnel import build_funnel_filters


class _FakeI18n:
    def get(self, key: str, **kwargs):
        messages = {
            "funnel-results-title": "We found for you:",
            "results-show-more": "🔄 Show more",
            "results-show-more-remaining": f"🔄 Show more ({kwargs.get('remaining', 0)} left)",
            "results-service-unavailable": "Search service unavailable.",
            "results-no-results": "No matches.",
            "results-found": f"Found {kwargs.get('total', 0)} apartments",
            "results-found-range": (
                f"Found {kwargs.get('total', 0)} apartments "
                f"(showing {kwargs.get('start', 0)}–{kwargs.get('end', 0)})"
            ),
            "back": "Back",
        }
        return messages[key]


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
    filters = build_funnel_filters(rooms="any", budget="any", complex_name="Premier Fort Beach")
    assert filters["complex_name"] == "Premier Fort Beach"


def test_complex_name_any_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", complex_name="any")
    assert "complex_name" not in filters


def test_is_furnished_true():
    filters = build_funnel_filters(rooms="any", budget="any", is_furnished="yes")
    assert filters["is_furnished"] is True


def test_is_furnished_false():
    filters = build_funnel_filters(rooms="any", budget="any", is_furnished="no")
    assert filters["is_furnished"] is False


def test_is_furnished_none_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", is_furnished=None)
    assert "is_furnished" not in filters


def test_is_promotion_true():
    filters = build_funnel_filters(rooms="any", budget="any", is_promotion="yes")
    assert filters["is_promotion"] is True


def test_is_promotion_none_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", is_promotion=None)
    assert "is_promotion" not in filters


def test_combined_filters():
    """All filter types combined."""
    filters = build_funnel_filters(
        rooms="2bed",
        budget="high",
        complex_name="Premier Fort Beach",
        floor="mid",
        view="sea",
        is_furnished="yes",
        is_promotion="yes",
    )
    assert filters["rooms"] == 3
    assert filters["price_eur"] == {"gte": 100000, "lte": 150000}
    assert filters["complex_name"] == "Premier Fort Beach"
    assert filters["floor"] == {"gte": 2, "lte": 3}
    assert filters["view_tags"] == ["sea"]
    assert filters["is_furnished"] is True
    assert filters["is_promotion"] is True


# --- get_results_data integration (mocked svc) ---


@pytest.mark.asyncio
async def test_get_results_data_returns_apartments_list():
    """get_results_data returns structured apartment dicts for List widget."""
    from telegram_bot.dialogs.funnel import get_results_data

    results = [
        {
            "id": "apt-1",
            "payload": {
                "complex_name": "Sunrise Complex",
                "section": "B-2",
                "apartment_number": "105",
                "rooms": 1,
                "floor": 2,
                "area_m2": 42.0,
                "view_primary": "sea",
                "price_eur": 48500,
                "city": "Свети Влас",
            },
        }
    ]
    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(return_value=(results, 297, "next-uuid"))

    manager = SimpleNamespace(
        dialog_data={"property_type": "studio", "budget": "low"},
        middleware_data={"apartments_service": mock_svc},
    )

    result = await get_results_data(dialog_manager=manager)

    assert "apartments" in result
    assert len(result["apartments"]) == 1
    apt = result["apartments"][0]
    assert apt["complex_name"] == "Sunrise Complex"
    assert apt["section"] == "B-2"
    assert apt["apartment_number"] == "105"
    assert apt["price_formatted"] == "48 500"
    assert apt["property_type"] == "Студия"
    assert result["has_apartments"] is True
    assert result["has_more"] is True
    assert result["no_results"] is False
    assert result["title"] == "Найдено 297 апартаментов (показаны 1–1)"
    assert "296 осталось" in result["btn_more"]
    mock_svc.scroll_with_filters.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_results_data_no_results_sets_flag():
    """get_results_data sets no_results=True when empty."""
    from telegram_bot.dialogs.funnel import get_results_data

    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(return_value=([], 0, None))

    manager = SimpleNamespace(
        dialog_data={"property_type": "3bed", "budget": "luxury"},
        middleware_data={"apartments_service": mock_svc},
    )

    result = await get_results_data(dialog_manager=manager)
    assert result["apartments"] == []
    assert result["has_apartments"] is False
    assert result["no_results"] is True
    assert result["has_more"] is False


@pytest.mark.asyncio
async def test_get_results_data_no_service():
    from telegram_bot.dialogs.funnel import get_results_data

    manager = SimpleNamespace(
        dialog_data={"property_type": "any", "budget": "any"},
        middleware_data={},
    )

    result = await get_results_data(dialog_manager=manager)
    assert result["no_results"] is True
    assert "недоступен" in result["no_results_text"].lower()
    assert result["btn_back"] == "Назад"


@pytest.mark.asyncio
async def test_get_results_data_uses_i18n_strings():
    from telegram_bot.dialogs.funnel import get_results_data

    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(return_value=([], 12, "next"))

    manager = SimpleNamespace(
        dialog_data={"property_type": "any", "budget": "any"},
        middleware_data={"apartments_service": mock_svc, "i18n": _FakeI18n()},
    )

    result = await get_results_data(dialog_manager=manager)
    assert result["title"] == "Found 12 apartments"
    assert result["btn_more"] == "🔄 Show more"
    assert result["btn_back"] == "Back"


def test_section_filter():
    filters = build_funnel_filters(rooms="any", budget="any", section="D-1")
    assert filters["section"] == "D-1"


def test_section_any_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", section="any")
    assert "section" not in filters


def test_section_none_not_included():
    filters = build_funnel_filters(rooms="any", budget="any", section=None)
    assert "section" not in filters


def test_combined_with_section():
    filters = build_funnel_filters(
        rooms="2bed", budget="high", complex_name="Premier Fort Beach", section="C-2"
    )
    assert filters["rooms"] == 3
    assert filters["section"] == "C-2"
    assert filters["complex_name"] == "Premier Fort Beach"


@pytest.mark.asyncio
async def test_get_results_data_uses_i18n_range_and_remaining_when_results_exist():
    from telegram_bot.dialogs.funnel import get_results_data

    results = [
        {
            "id": "apt-1",
            "payload": {
                "complex_name": "Sunrise Complex",
                "rooms": 1,
                "floor": 2,
                "area_m2": 42.0,
                "view_primary": "Sea",
                "price_eur": 48500,
            },
        }
    ]
    mock_svc = MagicMock()
    mock_svc.scroll_with_filters = AsyncMock(return_value=(results, 12, "next"))

    manager = SimpleNamespace(
        dialog_data={"property_type": "any", "budget": "any", "scroll_page": 1},
        middleware_data={"apartments_service": mock_svc, "i18n": _FakeI18n()},
    )

    result = await get_results_data(dialog_manager=manager)
    assert result["title"] == "Found 12 apartments (showing 1–1)"
    assert result["btn_more"] == "🔄 Show more (11 left)"
    assert "apartments" in result
    assert len(result["apartments"]) == 1
