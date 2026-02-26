# tests/unit/services/test_apartment_models.py
"""Tests for apartment data models."""

from __future__ import annotations

import pytest

from telegram_bot.services.apartment_models import (
    ApartmentQueryParseResult,
    ApartmentRecord,
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
            "city": "Sunny Beach",
        }
        rec = ApartmentRecord.from_raw(row)
        assert rec.complex_name == "Premier Fort Beach"
        assert rec.city == "Sunny Beach"
        assert rec.rooms == 2
        assert rec.floor == 4
        assert rec.view_primary == "sea"
        assert rec.view_tags == ["sea"]
        assert rec.price_eur == 215000.0

    def test_from_raw_row_missing_city_defaults_to_empty(self) -> None:
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
            "city": "Elenite",
        }
        rec = ApartmentRecord.from_raw(row)
        payload = rec.to_payload()
        assert payload["complex_name"] == "Test"
        assert payload["city"] == "Elenite"
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
            (None, None, None, ["sea"], [], "MEDIUM"),
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
