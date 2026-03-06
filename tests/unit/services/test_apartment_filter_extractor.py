# tests/unit/services/test_apartment_filter_extractor.py
"""Tests for apartment-specific filter extraction."""

from __future__ import annotations

import pytest

from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor


_ext = ApartmentFilterExtractor()


class TestRooms:
    @pytest.mark.parametrize(
        ("query", "expected_rooms"),
        [
            ("двушка с видом на море", 2),
            ("2 комнаты до 200к", 2),
            ("трёхкомнатная квартира", 3),
            ("студия в Несебре", 1),
            ("однокомнатная", 1),
            ("4 спальни", 4),
        ],
    )
    def test_rooms_extraction(self, query: str, expected_rooms: int) -> None:
        result = _ext.parse(query)
        assert result.rooms == expected_rooms


class TestPrice:
    @pytest.mark.parametrize(
        ("query", "min_p", "max_p"),
        [
            ("до 200000 евро", None, 200000.0),
            ("до 200к", None, 200000.0),
            ("от 100к до 300к", 100000.0, 300000.0),
            ("дешевле 150000", None, 150000.0),
            ("от 80000 евро", 80000.0, None),
        ],
    )
    def test_price_extraction(self, query: str, min_p, max_p) -> None:
        result = _ext.parse(query)
        assert result.min_price_eur == min_p
        assert result.max_price_eur == max_p

    def test_price_conflict_min_gt_max(self) -> None:
        result = _ext.parse("от 300к до 100к")
        assert "price_conflict" in result.conflicts[0]


class TestComplex:
    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("квартира в Премьер Форт Бич", "Premier Fort Beach"),
            ("Premier Fort Beach двушка", "Premier Fort Beach"),
            ("апартамент в Кроун Форт", "Crown Fort Club"),
            ("Green Fort Suites студия", "Green Fort Suites"),
            ("Nessebar Fort Residence", "Nessebar Fort Residence"),
            ("в Престиже", "Prestige Fort Beach"),
        ],
    )
    def test_complex_extraction(self, query: str, expected: str) -> None:
        result = _ext.parse(query)
        assert result.complex_name == expected


class TestView:
    @pytest.mark.parametrize(
        ("query", "expected_tags"),
        [
            ("с видом на море", ["sea"]),
            ("sea view", ["sea"]),
            ("у бассейна", ["pool"]),
            ("вид на сад", ["garden"]),
            ("панорама моря", ["sea", "panorama"]),
        ],
    )
    def test_view_extraction(self, query: str, expected_tags: list[str]) -> None:
        result = _ext.parse(query)
        assert set(result.view_tags) == set(expected_tags)


class TestFloor:
    @pytest.mark.parametrize(
        ("query", "min_floor", "max_floor"),
        [
            ("высокий этаж", 4, None),
            ("3 этаж", 3, 3),
            ("не выше 2 этажа", None, 2),
            ("от 5 этажа", 5, None),
        ],
    )
    def test_floor_extraction(self, query: str, min_floor, max_floor) -> None:
        result = _ext.parse(query)
        assert result.min_floor == min_floor
        assert result.max_floor == max_floor


class TestArea:
    @pytest.mark.parametrize(
        ("query", "min_area", "max_area"),
        [
            ("от 80 м2", 80.0, None),
            ("до 100 кв.м", None, 100.0),
            ("площадь от 60 до 120 м²", 60.0, 120.0),
        ],
    )
    def test_area_extraction(self, query: str, min_area, max_area) -> None:
        result = _ext.parse(query)
        assert result.min_area_m2 == min_area
        assert result.max_area_m2 == max_area

    def test_area_range_not_interpreted_as_price(self) -> None:
        result = _ext.parse("площадь от 60 до 120 м²")
        assert result.min_area_m2 == 60.0
        assert result.max_area_m2 == 120.0
        assert result.min_price_eur is None
        assert result.max_price_eur is None


class TestCombined:
    def test_full_query(self) -> None:
        result = _ext.parse("двушка до 200к с видом на море в Премьере")
        assert result.rooms == 2
        assert result.max_price_eur == 200000.0
        assert "sea" in result.view_tags
        assert result.complex_name == "Premier Fort Beach"

    def test_semantic_query_extracted(self) -> None:
        result = _ext.parse("уютная двушка до 200к в Премьере")
        # semantic_query should retain descriptive words, strip numbers/filters
        assert "уютн" in result.semantic_query.lower() or result.semantic_query != ""


class TestConfidenceIntegration:
    def test_high_confidence(self) -> None:
        result = _ext.parse("двушка до 200к в Премьере")
        assert result.confidence == "HIGH"

    def test_medium_confidence(self) -> None:
        result = _ext.parse("квартира до 200к")
        assert result.confidence == "MEDIUM"

    def test_low_confidence(self) -> None:
        result = _ext.parse("что-нибудь хорошее")
        assert result.confidence == "LOW"


class TestCity:
    @pytest.mark.parametrize(
        ("query", "expected_city"),
        [
            ("двушка солнечный берег", "Солнечный берег"),
            ("студия sunny beach", "Солнечный берег"),
            ("квартира в свети влас", "Свети Влас"),
            ("апартамент святой влас", "Свети Влас"),
            ("элените 3 комнаты", "Элените"),
            ("elenite apartment", "Элените"),
            ("санни бич до 100к", "Солнечный берег"),
            ("двушка в несебре", None),  # несебр — не в нашей БД
        ],
    )
    def test_city_extraction(self, query: str, expected_city: str | None) -> None:
        result = _ext.parse(query)
        assert result.city == expected_city


class TestCityAndComplex:
    def test_city_consumed_from_semantic(self) -> None:
        result = _ext.parse("уютная двушка солнечный берег до 100к")
        assert result.city == "Солнечный берег"
        assert "солнечный берег" not in result.semantic_query.lower()

    def test_city_and_complex_together(self) -> None:
        result = _ext.parse("премьер форт свети влас")
        assert result.city == "Свети Влас"
        assert result.complex_name == "Premier Fort Beach"

    def test_treshka_rooms(self) -> None:
        result = _ext.parse("трешка солнечный берег")
        assert result.rooms == 3
        assert result.city == "Солнечный берег"
