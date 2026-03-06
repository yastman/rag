"""Tests for ApartmentSearchFilters Pydantic models."""

from __future__ import annotations

from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)


class TestHardFilters:
    def test_defaults_all_none(self) -> None:
        f = HardFilters()
        assert f.city is None
        assert f.rooms is None
        assert f.min_price_eur is None

    def test_price_range_auto_swap(self) -> None:
        f = HardFilters(min_price_eur=200000, max_price_eur=100000)
        assert f.min_price_eur == 100000
        assert f.max_price_eur == 200000

    def test_area_range_auto_swap(self) -> None:
        f = HardFilters(min_area_m2=120, max_area_m2=60)
        assert f.min_area_m2 == 60
        assert f.max_area_m2 == 120

    def test_floor_range_auto_swap(self) -> None:
        f = HardFilters(min_floor=5, max_floor=2)
        assert f.min_floor == 2
        assert f.max_floor == 5

    def test_no_swap_when_valid(self) -> None:
        f = HardFilters(min_price_eur=100000, max_price_eur=200000)
        assert f.min_price_eur == 100000
        assert f.max_price_eur == 200000

    def test_to_filters_dict_full(self) -> None:
        f = HardFilters(
            city="Солнечный берег",
            rooms=2,
            min_price_eur=50000,
            max_price_eur=100000,
            view_tags=["sea"],
        )
        d = f.to_filters_dict()
        assert d is not None
        assert d["city"] == "Солнечный берег"
        assert d["rooms"] == 2
        assert d["price_eur"]["gte"] == 50000
        assert d["price_eur"]["lte"] == 100000
        assert d["view_tags"] == ["sea"]

    def test_to_filters_dict_empty(self) -> None:
        f = HardFilters()
        assert f.to_filters_dict() is None

    def test_to_filters_dict_partial_price(self) -> None:
        f = HardFilters(max_price_eur=100000)
        d = f.to_filters_dict()
        assert d is not None
        assert "gte" not in d["price_eur"]
        assert d["price_eur"]["lte"] == 100000


class TestSoftPreferences:
    def test_to_semantic_parts(self) -> None:
        s = SoftPreferences(near_sea=True, spacious=True)
        parts = s.to_semantic_parts()
        assert "близко к морю" in parts
        assert "просторная квартира" in parts

    def test_empty_semantic_parts(self) -> None:
        s = SoftPreferences()
        assert s.to_semantic_parts() == []

    def test_budget_friendly_semantic(self) -> None:
        s = SoftPreferences(budget_friendly=True)
        parts = s.to_semantic_parts()
        assert any("бюджет" in p or "недорого" in p for p in parts)


class TestExtractionMeta:
    def test_defaults(self) -> None:
        m = ExtractionMeta()
        assert m.source == "regex"
        assert m.confidence == "LOW"
        assert m.score == 0
        assert m.missing_fields == []

    def test_custom_source(self) -> None:
        m = ExtractionMeta(source="llm", confidence="HIGH")
        assert m.source == "llm"
        assert m.confidence == "HIGH"


class TestApartmentSearchFilters:
    def test_defaults(self) -> None:
        f = ApartmentSearchFilters()
        assert f.hard.city is None
        assert f.soft.near_sea is False
        assert f.meta.source == "regex"

    def test_build_semantic_query_with_remainder(self) -> None:
        f = ApartmentSearchFilters(
            soft=SoftPreferences(near_sea=True),
            meta=ExtractionMeta(semantic_remainder="уютная"),
        )
        q = f.build_semantic_query()
        assert "уютная" in q
        assert "близко к морю" in q

    def test_build_semantic_query_empty(self) -> None:
        f = ApartmentSearchFilters()
        assert f.build_semantic_query() == "апартамент"

    def test_build_semantic_query_remainder_only(self) -> None:
        f = ApartmentSearchFilters(meta=ExtractionMeta(semantic_remainder="просторная с видом"))
        q = f.build_semantic_query()
        assert "просторная с видом" in q
