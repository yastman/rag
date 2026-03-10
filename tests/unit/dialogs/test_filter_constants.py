"""Tests for filter_constants — shared constants and helpers for filter dialog and funnel."""

from __future__ import annotations

import pytest

from telegram_bot.dialogs.filter_constants import (
    AREA_MAP,
    BUDGET_DISPLAY,
    BUDGET_MAP,
    BUDGET_OPTIONS,
    CITY_OPTIONS,
    FIELD_TO_FILTER_KEY,
    FLOOR_MAP,
    ROOMS_DISPLAY,
    ROOMS_OPTIONS,
    VIEW_DISPLAY,
    build_filters_dict,
    coerce_filter_value,
)


# ============================================================
# Constants sanity checks
# ============================================================


class TestConstants:
    def test_city_options_non_empty(self):
        assert len(CITY_OPTIONS) > 0

    def test_budget_map_has_5_tiers(self):
        assert set(BUDGET_MAP.keys()) == {"low", "mid", "high", "premium", "luxury"}

    def test_budget_display_matches_budget_map(self):
        assert set(BUDGET_DISPLAY.keys()) == set(BUDGET_MAP.keys())

    def test_budget_options_label_value_pairs(self):
        assert all(len(item) == 2 for item in BUDGET_OPTIONS)
        labels = [label for label, _ in BUDGET_OPTIONS]
        assert "До 50 000 €" in labels

    def test_rooms_options_has_studio(self):
        room_labels = [label for label, _ in ROOMS_OPTIONS]
        assert "Студия" in room_labels

    def test_rooms_display_has_standard_rooms(self):
        assert ROOMS_DISPLAY[2] == "1-спальня"
        assert ROOMS_DISPLAY[3] == "2-спальни"

    def test_floor_map_has_4_tiers(self):
        assert set(FLOOR_MAP.keys()) == {"low", "mid", "high", "top"}

    def test_area_map_has_tiers(self):
        assert "small" in AREA_MAP
        assert "xxlarge" in AREA_MAP

    def test_view_display_has_sea(self):
        assert "sea" in VIEW_DISPLAY

    def test_field_to_filter_key_all_9(self):
        expected_fields = {
            "city",
            "rooms",
            "budget",
            "view",
            "area",
            "floor",
            "complex",
            "furnished",
            "promotion",
        }
        assert set(FIELD_TO_FILTER_KEY.keys()) == expected_fields

    def test_budget_field_maps_to_price_eur(self):
        assert FIELD_TO_FILTER_KEY["budget"] == "price_eur"

    def test_furnished_maps_to_is_furnished(self):
        assert FIELD_TO_FILTER_KEY["furnished"] == "is_furnished"


# ============================================================
# coerce_filter_value
# ============================================================


class TestCoerceFilterValue:
    @pytest.mark.parametrize(
        "field,value,expected",
        [
            ("city", "Бургас", "Бургас"),
            ("city", "", None),
            ("rooms", "2", 2),
            ("rooms", "3", 3),
            ("rooms", "abc", None),
            ("floor", "5", 5),
            ("floor", "bad", None),
            ("area", "60", {"gte": 60}),
            ("area", "bad", None),
            ("view", "sea", ["sea"]),
            ("view", "", None),
            ("complex", "Premier Fort", "Premier Fort"),
            ("complex", "", None),
            ("furnished", "true", True),
            ("furnished", "false", False),
            ("furnished", "", None),
            ("promotion", "true", True),
            ("promotion", "false", False),
            ("promotion", "", None),
            ("budget", "mid", {"gte": 50_000, "lte": 100_000}),
            ("budget", "low", {"lte": 50_000}),
            ("budget", "luxury", {"gte": 200_000}),
            ("budget", "unknown", None),
            ("budget", "", None),
        ],
    )
    def test_coerce(self, field, value, expected):
        assert coerce_filter_value(field, value) == expected


# ============================================================
# build_filters_dict
# ============================================================


class TestBuildFiltersDict:
    def test_empty_input_returns_empty_dict(self):
        result = build_filters_dict({})
        assert result == {}

    def test_city_passthrough(self):
        result = build_filters_dict({"city": "Солнечный берег"})
        assert result == {"city": "Солнечный берег"}

    def test_budget_maps_to_price_eur(self):
        result = build_filters_dict({"budget": "mid"})
        assert "price_eur" in result
        assert "budget" not in result
        assert result["price_eur"] == {"gte": 50_000, "lte": 100_000}

    def test_rooms_passthrough(self):
        result = build_filters_dict({"rooms": 2})
        assert result["rooms"] == 2

    def test_none_values_excluded(self):
        result = build_filters_dict({"city": None, "rooms": 2})
        assert "city" not in result
        assert result["rooms"] == 2

    def test_empty_string_excluded(self):
        result = build_filters_dict({"city": ""})
        assert "city" not in result

    def test_any_value_excluded(self):
        result = build_filters_dict({"city": "any"})
        assert "city" not in result

    def test_combined_filters(self):
        result = build_filters_dict({"city": "Несебр", "budget": "high", "rooms": 3})
        assert result["city"] == "Несебр"
        assert result["price_eur"] == {"gte": 100_000, "lte": 150_000}
        assert result["rooms"] == 3
        assert "budget" not in result
