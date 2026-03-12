# tests/unit/services/test_apartment_models.py
"""Tests for apartment data models."""

from __future__ import annotations

import pydantic
import pytest

from telegram_bot.services.apartment_models import (
    ApartmentQueryParseResult,
    ApartmentRecord,
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
    compute_confidence,
)


class TestApartmentRecord:
    def test_from_raw_row_basic(self) -> None:
        row = {
            "complex_name": "Premier Fort Beach",
            "section": "D-1",
            "apartment_number": "248",
            "rooms": 2,
            "floor_label": "4",
            "area_m2": 78.66,
            "view_raw": "sea",
            "price_eur": 215000.0,
            "price_bgn": 420503.45,
            "is_furnished": True,
            "has_floor_plan": True,
            "has_photo": True,
            "city": "Солнечный берег",
        }
        rec = ApartmentRecord.from_raw(row)
        assert rec.complex_name == "Premier Fort Beach"
        assert rec.city == "Солнечный берег"
        assert rec.rooms == 2
        assert rec.floor == 4
        assert rec.view_primary == "sea"
        assert rec.view_tags == ["sea"]
        assert rec.price_eur == 215000.0

    def test_from_raw_row_missing_city_defaults_to_empty(self) -> None:
        row = {
            "complex_name": "Test",
            "section": "D-1",
            "apartment_number": "248",
            "rooms": 2,
            "floor_label": "4",
            "area_m2": 78.66,
            "view_raw": "sea",
            "price_eur": 215000.0,
            "price_bgn": 420503.45,
            "is_furnished": True,
            "has_floor_plan": True,
            "has_photo": True,
        }
        rec = ApartmentRecord.from_raw(row)
        assert rec.city == ""

    def test_from_raw_ground_floor(self) -> None:
        row = {
            "floor_label": "gr.",
            "rooms": 1,
            "price_eur": 80000.0,
            "complex_name": "Test",
            "section": "A",
            "apartment_number": "1",
            "area_m2": 40.0,
            "view_raw": "garden",
            "price_bgn": 156466.0,
            "is_furnished": False,
            "has_floor_plan": True,
            "has_photo": False,
        }
        rec = ApartmentRecord.from_raw(row)
        assert rec.floor == 0
        assert rec.floor_label == "gr."

    def test_view_normalization_compound(self) -> None:
        row = {
            "view_raw": "ultra sea panorama",
            "complex_name": "T",
            "section": "A",
            "apartment_number": "1",
            "rooms": 3,
            "floor_label": "2",
            "area_m2": 100.0,
            "price_eur": 300000.0,
            "price_bgn": 0,
            "is_furnished": True,
            "has_floor_plan": True,
            "has_photo": True,
        }
        rec = ApartmentRecord.from_raw(row)
        assert rec.view_primary == "ultra_sea_panorama"
        assert "sea" in rec.view_tags

    def test_view_normalization_slash(self) -> None:
        row = {
            "view_raw": "sea/garden",
            "complex_name": "T",
            "section": "A",
            "apartment_number": "1",
            "rooms": 2,
            "floor_label": "1",
            "area_m2": 80.0,
            "price_eur": 200000.0,
            "price_bgn": 0,
            "is_furnished": False,
            "has_floor_plan": True,
            "has_photo": True,
        }
        rec = ApartmentRecord.from_raw(row)
        assert rec.view_primary == "sea"
        assert set(rec.view_tags) == {"sea", "garden"}

    def test_to_description(self) -> None:
        row = {
            "complex_name": "Crown Fort Club",
            "section": "F-2",
            "apartment_number": "547",
            "rooms": 1,
            "floor_label": "gr.",
            "area_m2": 37.92,
            "view_raw": "garden",
            "price_eur": 81500.0,
            "price_bgn": 159400.15,
            "is_furnished": True,
            "has_floor_plan": True,
            "has_photo": False,
        }
        rec = ApartmentRecord.from_raw(row)
        desc = rec.to_description()
        assert "Crown Fort Club" in desc
        assert "37.92" in desc
        assert "81 500" in desc or "81500" in desc

    def test_to_payload(self) -> None:
        row = {
            "complex_name": "Test",
            "section": "A-1",
            "apartment_number": "10",
            "rooms": 2,
            "floor_label": "3",
            "area_m2": 70.0,
            "view_raw": "pool/sea",
            "price_eur": 150000.0,
            "price_bgn": 293000.0,
            "is_furnished": True,
            "has_floor_plan": True,
            "has_photo": True,
            "city": "Элените",
        }
        rec = ApartmentRecord.from_raw(row)
        payload = rec.to_payload()
        assert payload["complex_name"] == "Test"
        assert payload["city"] == "Элените"
        assert payload["rooms"] == 2
        assert payload["floor"] == 3
        assert payload["price_eur"] == 150000.0
        assert "sea" in payload["view_tags"]
        assert payload["view_primary"] == "pool"

    def test_from_raw_parses_string_booleans(self) -> None:
        row = {
            "complex_name": "Test",
            "section": "A-1",
            "apartment_number": "10",
            "rooms": 2,
            "floor_label": "3",
            "area_m2": 70.0,
            "view_raw": "pool/sea",
            "price_eur": 150000.0,
            "price_bgn": 293000.0,
            "is_furnished": "False",
            "has_floor_plan": "True",
            "has_photo": "0",
        }
        rec = ApartmentRecord.from_raw(row)
        assert rec.is_furnished is False
        assert rec.has_floor_plan is True
        assert rec.has_photo is False


class TestApartmentQueryParseResult:
    def test_defaults(self) -> None:
        r = ApartmentQueryParseResult(raw_query="test")
        assert r.confidence == "LOW"
        assert r.score == 0
        assert r.conflicts == []

    def test_to_filters_dict(self) -> None:
        r = ApartmentQueryParseResult(
            rooms=2,
            max_price_eur=200000.0,
            raw_query="двушка до 200к",
        )
        filters = r.to_filters_dict()
        assert filters["rooms"] == 2
        assert filters["price_eur"]["lte"] == 200000.0
        assert "area_m2" not in filters


class TestComputeConfidence:
    @pytest.mark.parametrize(
        ("rooms", "max_price", "complex_name", "view_tags", "conflicts", "expected"),
        [
            (2, 200000.0, "Premier Fort Beach", [], [], "HIGH"),
            (2, None, None, ["sea"], [], "MEDIUM"),
            (None, 200000.0, None, [], [], "MEDIUM"),
            (2, None, None, [], [], "MEDIUM"),
            (None, None, None, ["sea"], [], "LOW"),  # view only, no hard/critical → LOW
            (None, None, None, [], [], "LOW"),
            (2, 200000.0, "Premier", [], ["min>max"], "LOW"),
        ],
    )
    def test_confidence_levels(
        self,
        rooms,
        max_price,
        complex_name,
        view_tags,
        conflicts,
        expected,
    ) -> None:
        r = ApartmentQueryParseResult(
            rooms=rooms,
            max_price_eur=max_price,
            complex_name=complex_name,
            view_tags=view_tags or [],
            conflicts=conflicts,
            raw_query="test",
        )
        result = compute_confidence(r)
        assert result.confidence == expected


class TestComputeConfidenceV2:
    """Updated confidence with critical slots check."""

    def test_high_with_city_and_hard(self) -> None:
        r = ApartmentQueryParseResult(rooms=2, max_price_eur=100000, city="Солнечный берег")
        result = compute_confidence(r)
        assert result.confidence == "HIGH"

    def test_high_with_complex_and_hard(self) -> None:
        r = ApartmentQueryParseResult(
            rooms=2, max_price_eur=200000, complex_name="Premier Fort Beach"
        )
        result = compute_confidence(r)
        assert result.confidence == "HIGH"

    def test_medium_rooms_only(self) -> None:
        r = ApartmentQueryParseResult(rooms=2)
        result = compute_confidence(r)
        assert result.confidence == "MEDIUM"

    def test_medium_city_only(self) -> None:
        r = ApartmentQueryParseResult(city="Свети Влас")
        result = compute_confidence(r)
        assert result.confidence == "MEDIUM"

    def test_low_no_filters(self) -> None:
        r = ApartmentQueryParseResult()
        result = compute_confidence(r)
        assert result.confidence == "LOW"

    def test_low_on_conflict(self) -> None:
        r = ApartmentQueryParseResult(rooms=2, city="Элените", conflicts=["price_conflict:min>max"])
        result = compute_confidence(r)
        assert result.confidence == "LOW"

    def test_missing_fields_tracked(self) -> None:
        r = ApartmentQueryParseResult(rooms=2)
        result = compute_confidence(r)
        assert "city" in result.missing_fields or "complex_name" in result.missing_fields

    def test_missing_fields_empty_when_critical_present(self) -> None:
        r = ApartmentQueryParseResult(rooms=2, city="Элените")
        result = compute_confidence(r)
        assert result.missing_fields == []


class TestHybridDescription:
    def test_has_structured_prefix(self) -> None:
        record = ApartmentRecord(
            complex_name="Test",
            city="",
            section="A",
            apartment_number="1",
            rooms=2,
            floor=3,
            floor_label="3",
            area_m2=65.0,
            view_primary="sea",
            view_tags=["sea"],
            price_eur=120000.0,
            price_bgn=234000.0,
            is_furnished=False,
            has_floor_plan=False,
            has_photo=False,
        )
        text = record.to_hybrid_description()
        assert text.startswith("[2BR|65.0m2|120kEUR]")

    def test_has_natural_language_body(self) -> None:
        record = ApartmentRecord(
            complex_name="Premier Fort Beach",
            city="Sunny Beach",
            section="D-1",
            apartment_number="248",
            rooms=2,
            floor=4,
            floor_label="4",
            area_m2=78.66,
            view_primary="sea",
            view_tags=["sea"],
            price_eur=215000.0,
            price_bgn=420503.45,
            is_furnished=False,
            has_floor_plan=False,
            has_photo=False,
        )
        text = record.to_hybrid_description()
        assert "Premier Fort Beach" in text
        assert "2 комнаты" in text

    def test_promotion_marker(self) -> None:
        record = ApartmentRecord(
            complex_name="Test",
            city="",
            section="A",
            apartment_number="1",
            rooms=1,
            floor=2,
            floor_label="2",
            area_m2=30.0,
            view_primary="pool",
            view_tags=["pool"],
            price_eur=50000.0,
            price_bgn=97000.0,
            is_furnished=True,
            has_floor_plan=False,
            has_photo=False,
            is_promotion=True,
            old_price_eur=60000.0,
        )
        text = record.to_hybrid_description()
        assert "Акция" in text


class TestHardFiltersLiteralConstraints:
    """Tests for Literal city, ge/le constraints, and Field descriptions on HardFilters."""

    def test_valid_city_accepted(self) -> None:
        hf = HardFilters(city="Солнечный берег")
        assert hf.city == "Солнечный берег"

    def test_valid_city_sveti_vlas(self) -> None:
        hf = HardFilters(city="Свети Влас")
        assert hf.city == "Свети Влас"

    def test_valid_city_elenite(self) -> None:
        hf = HardFilters(city="Элените")
        assert hf.city == "Элените"

    def test_invalid_city_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="city"):
            HardFilters(city="Бургас")

    def test_city_none_allowed(self) -> None:
        hf = HardFilters(city=None)
        assert hf.city is None

    def test_rooms_ge_1(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="rooms"):
            HardFilters(rooms=0)

    def test_rooms_le_5(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="rooms"):
            HardFilters(rooms=6)

    def test_rooms_valid_range(self) -> None:
        for n in (1, 2, 3, 4, 5):
            hf = HardFilters(rooms=n)
            assert hf.rooms == n

    def test_min_price_ge_1000(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="min_price_eur"):
            HardFilters(min_price_eur=500)

    def test_max_price_ge_1000(self) -> None:
        with pytest.raises(pydantic.ValidationError, match="max_price_eur"):
            HardFilters(max_price_eur=999)

    def test_price_valid(self) -> None:
        hf = HardFilters(min_price_eur=50000, max_price_eur=200000)
        assert hf.min_price_eur == 50000
        assert hf.max_price_eur == 200000

    def test_price_range_auto_swap(self) -> None:
        """Inverted price range is auto-corrected by fix_ranges validator."""
        hf = HardFilters(min_price_eur=200000, max_price_eur=100000)
        assert hf.min_price_eur == 100000
        assert hf.max_price_eur == 200000

    def test_area_range_auto_swap(self) -> None:
        hf = HardFilters(min_area_m2=120, max_area_m2=60)
        assert hf.min_area_m2 == 60
        assert hf.max_area_m2 == 120

    def test_floor_range_auto_swap(self) -> None:
        hf = HardFilters(min_floor=5, max_floor=2)
        assert hf.min_floor == 2
        assert hf.max_floor == 5

    def test_defaults_all_none(self) -> None:
        hf = HardFilters()
        assert hf.city is None
        assert hf.rooms is None
        assert hf.min_price_eur is None
        assert hf.max_price_eur is None
        assert hf.min_area_m2 is None
        assert hf.max_area_m2 is None
        assert hf.view_tags == []
        assert hf.is_furnished is None

    def test_to_filters_dict_empty(self) -> None:
        hf = HardFilters()
        assert hf.to_filters_dict() is None

    def test_to_filters_dict_rooms_and_price(self) -> None:
        hf = HardFilters(rooms=3, max_price_eur=200000)
        d = hf.to_filters_dict()
        assert d is not None
        assert d["rooms"] == 3
        assert d["price_eur"] == {"lte": 200000}

    def test_to_filters_dict_area_range(self) -> None:
        hf = HardFilters(min_area_m2=60, max_area_m2=120)
        d = hf.to_filters_dict()
        assert d is not None
        assert d["area_m2"] == {"gte": 60, "lte": 120}

    def test_field_descriptions_present(self) -> None:
        """All key fields have descriptions for instructor LLM guidance."""
        schema = HardFilters.model_json_schema()
        props = schema["properties"]
        for field_name in (
            "city",
            "rooms",
            "min_price_eur",
            "max_price_eur",
            "min_area_m2",
            "complex_name",
            "view_tags",
            "is_furnished",
        ):
            assert "description" in props[field_name], f"{field_name} missing description"

    def test_rooms_description_mentions_slang(self) -> None:
        """Rooms description must explain двушка/трёшка convention."""
        schema = HardFilters.model_json_schema()
        desc = schema["properties"]["rooms"]["description"]
        assert "двушка" in desc
        assert "трёшка" in desc


class TestApartmentSearchFiltersSchema:
    """Tests for the full ApartmentSearchFilters Pydantic schema (instructor input)."""

    def test_default_construction(self) -> None:
        f = ApartmentSearchFilters()
        assert f.hard.city is None
        assert f.soft.near_sea is False
        assert f.meta.source == "regex"

    def test_full_construction(self) -> None:
        f = ApartmentSearchFilters(
            hard=HardFilters(city="Элените", rooms=3, max_price_eur=150000),
            soft=SoftPreferences(near_sea=True, budget_friendly=True, sort_bias="price_asc"),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        assert f.hard.city == "Элените"
        assert f.hard.rooms == 3
        assert f.soft.near_sea is True
        assert f.soft.sort_bias == "price_asc"
        assert f.meta.confidence == "HIGH"

    def test_build_semantic_query_with_preferences(self) -> None:
        f = ApartmentSearchFilters(
            soft=SoftPreferences(near_sea=True, spacious=True),
            meta=ExtractionMeta(semantic_remainder="у моря"),
        )
        q = f.build_semantic_query()
        assert "у моря" in q
        assert "близко к морю" in q

    def test_build_semantic_query_fallback(self) -> None:
        f = ApartmentSearchFilters()
        assert f.build_semantic_query() == "апартамент"

    def test_sort_bias_literal_values(self) -> None:
        for bias in ("price_asc", "price_desc", "area_desc", "floor_desc", "relevance"):
            sp = SoftPreferences(sort_bias=bias)  # type: ignore[arg-type]
            assert sp.sort_bias == bias

    def test_sort_bias_invalid_rejected(self) -> None:
        with pytest.raises(pydantic.ValidationError):
            SoftPreferences(sort_bias="invalid_sort")  # type: ignore[arg-type]

    def test_extraction_meta_source_literal(self) -> None:
        for src in ("regex", "llm", "hybrid"):
            m = ExtractionMeta(source=src)  # type: ignore[arg-type]
            assert m.source == src

    def test_extraction_meta_confidence_literal(self) -> None:
        for c in ("HIGH", "MEDIUM", "LOW"):
            m = ExtractionMeta(confidence=c)  # type: ignore[arg-type]
            assert m.confidence == c
