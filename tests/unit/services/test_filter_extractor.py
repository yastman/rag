"""Unit tests for FilterExtractor service."""

import pytest

from telegram_bot.services.filter_extractor import FilterExtractor


# Read-only: safe to share across all tests.
_ext = FilterExtractor()


# ---------------------------------------------------------------------------
# Price
# ---------------------------------------------------------------------------
class TestFilterExtractorPrice:
    """Tests for price filter extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("квартира дешевле 100000", {"price": {"lt": 100000}}),
            ("квартира до 50000 евро", {"price": {"lt": 50000}}),
            ("цена меньше 80000", {"price": {"lt": 80000}}),
            ("квартира < 120000", {"price": {"lt": 120000}}),
            ("квартира <120000", {"price": {"lt": 120000}}),
            ("не дороже 75000", {"price": {"lt": 75000}}),
        ],
    )
    def test_price_less_than(self, query: str, expected: dict) -> None:
        assert _ext.extract_filters(query) == expected

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("квартира дороже 50000", {"price": {"gt": 50000}}),
            ("квартира от 60000", {"price": {"gt": 60000}}),
            ("цена больше 45000", {"price": {"gt": 45000}}),
            ("квартира > 90000", {"price": {"gt": 90000}}),
            ("квартира >90000", {"price": {"gt": 90000}}),
        ],
    )
    def test_price_greater_than(self, query: str, expected: dict) -> None:
        assert _ext.extract_filters(query) == expected

    def test_price_range_pattern_order(self) -> None:
        result = _ext.extract_filters("квартира от 50000 до 100000")
        assert result["price"] == {"gte": 50000, "lte": 100000}

    def test_price_range_using_dashes(self) -> None:
        result = _ext.extract_filters("квартира 50000-100000")
        assert "price" not in result

    def test_price_k_suffix(self) -> None:
        assert _ext.extract_filters("квартира до 100к") == {"price": {"lt": 100000}}

    def test_price_with_spaces_in_number(self) -> None:
        assert _ext.extract_filters("квартира дешевле 100 000")["price"] == {"lt": 100000}

    def test_no_price_filter(self) -> None:
        assert "price" not in _ext.extract_filters("двукомнатная квартира в Бургасе")


# ---------------------------------------------------------------------------
# Rooms
# ---------------------------------------------------------------------------
class TestFilterExtractorRooms:
    """Tests for rooms filter extraction."""

    @pytest.mark.parametrize(
        ("query", "rooms"),
        [
            ("3 комнаты в Варне", 3),
            ("2-комнатная квартира", 2),
            ("4комнатная квартира", 4),
        ],
    )
    def test_rooms_digit(self, query: str, rooms: int) -> None:
        assert _ext.extract_filters(query)["rooms"] == rooms

    @pytest.mark.parametrize(
        ("query", "rooms"),
        [
            ("однокомнатная квартира", 1),
            ("двукомнатная квартира", 2),
            ("трехкомнатная квартира", 3),
            ("четырехкомнатная квартира", 4),
            ("пятикомнатная квартира", 5),
        ],
    )
    def test_rooms_word(self, query: str, rooms: int) -> None:
        assert _ext.extract_filters(query)["rooms"] == rooms

    def test_rooms_dvuhkomnatnaya_not_matched(self) -> None:
        """Regex matches 'дву', not 'двух'."""
        assert "rooms" not in _ext.extract_filters("двухкомнатная квартира")

    @pytest.mark.parametrize(
        "query",
        ["студия в центре", "Студия у моря"],
    )
    def test_rooms_studiya(self, query: str) -> None:
        assert _ext.extract_filters(query)["rooms"] == 1

    def test_no_rooms_filter(self) -> None:
        assert "rooms" not in _ext.extract_filters("квартира в Бургасе до 50000")


# ---------------------------------------------------------------------------
# City
# ---------------------------------------------------------------------------
class TestFilterExtractorCity:
    """Tests for city filter extraction."""

    @pytest.mark.parametrize(
        ("query", "city"),
        [
            ("квартира в Солнечный берег", "Солнечный берег"),
            ("квартира в Несебр", "Несебр"),
            ("квартира в Бургас", "Бургас"),
            ("квартира в Варна", "Варна"),
            ("квартира в София", "София"),
            ("квартира в Поморие", "Поморие"),
            ("квартира в Созополь", "Созополь"),
        ],
    )
    def test_city_known(self, query: str, city: str) -> None:
        assert _ext.extract_filters(query)["city"] == city

    @pytest.mark.parametrize(
        ("query", "city"),
        [
            ("квартира в ВАРНА", "Варна"),
            ("квартира в бургас", "Бургас"),
        ],
    )
    def test_city_case_insensitive(self, query: str, city: str) -> None:
        assert _ext.extract_filters(query)["city"] == city

    @pytest.mark.parametrize(
        "query",
        ["двукомнатная квартира до 50000", "квартира в Пловдив"],
    )
    def test_no_city_filter(self, query: str) -> None:
        assert "city" not in _ext.extract_filters(query)


# ---------------------------------------------------------------------------
# Distance to sea
# ---------------------------------------------------------------------------
class TestFilterExtractorDistanceToSea:
    """Tests for distance to sea filter extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("квартира до 500м до моря", {"lte": 500}),
            ("не дальше 600м от пляжа", {"lte": 600}),
            ("квартира в 400м от моря", {"lte": 400}),
            ("не дальше 300 метров от пляжа", {"lte": 300}),
            ("до 200м до пляжа", {"lte": 200}),
        ],
    )
    def test_distance_meters(self, query: str, expected: dict) -> None:
        assert _ext.extract_filters(query)["distance_to_sea"] == expected

    @pytest.mark.parametrize(
        "query",
        ["квартира на первая линия", "квартира у моря"],
    )
    def test_distance_near_sea(self, query: str) -> None:
        assert _ext.extract_filters(query)["distance_to_sea"] == {"lte": 200}

    def test_no_distance_filter(self) -> None:
        assert "distance_to_sea" not in _ext.extract_filters(
            "двукомнатная квартира в Бургасе"
        )


# ---------------------------------------------------------------------------
# Furniture
# ---------------------------------------------------------------------------
class TestFilterExtractorFurniture:
    """Tests for furniture filter extraction."""

    @pytest.mark.parametrize(
        "query",
        [
            "квартира с мебелью",
            "меблированная квартира",
            "квартира обставлена",
            "квартира С МЕБЕЛЬЮ",
        ],
    )
    def test_furniture_present(self, query: str) -> None:
        assert _ext.extract_filters(query)["furniture"] == "Есть"

    def test_no_furniture_filter(self) -> None:
        assert "furniture" not in _ext.extract_filters("квартира в Варне")


# ---------------------------------------------------------------------------
# Year-round
# ---------------------------------------------------------------------------
class TestFilterExtractorYearRound:
    """Tests for year_round filter extraction."""

    @pytest.mark.parametrize(
        "query",
        [
            "круглогодичная квартира",
            "квартира для проживания круглый год",
            "квартира где зимой можно жить",
            "комплекс зимой работает",
        ],
    )
    def test_year_round_present(self, query: str) -> None:
        assert _ext.extract_filters(query)["year_round"] == "Да"

    def test_no_year_round_filter(self) -> None:
        assert "year_round" not in _ext.extract_filters("квартира в Варне")


# ---------------------------------------------------------------------------
# Area
# ---------------------------------------------------------------------------
class TestFilterExtractorArea:
    """Tests for area filter extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("квартира больше 50 м2", {"gte": 50}),
            ("квартира от 60 кв.м", {"gte": 60}),
            ("квартира меньше 40 м", {"lte": 40}),
            ("квартира до 80 кв", {"lte": 80}),
        ],
    )
    def test_area(self, query: str, expected: dict) -> None:
        assert _ext.extract_filters(query)["area"] == expected

    def test_no_area_filter(self) -> None:
        assert "area" not in _ext.extract_filters("двукомнатная квартира")


# ---------------------------------------------------------------------------
# Floor
# ---------------------------------------------------------------------------
class TestFilterExtractorFloor:
    """Tests for floor filter extraction."""

    @pytest.mark.parametrize(
        ("query", "floor"),
        [
            ("квартира на 4 этаж", 4),
            ("квартира на 3 этаже", 3),
            ("квартира на 5", 5),
        ],
    )
    def test_floor(self, query: str, floor: int) -> None:
        assert _ext.extract_filters(query)["floor"] == floor

    def test_no_floor_filter(self) -> None:
        assert "floor" not in _ext.extract_filters("двукомнатная квартира в Бургасе")


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------
class TestFilterExtractorMaintenance:
    """Tests for maintenance cost filter extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("квартира с поддержка до 10 евро", {"lte": 10.0}),
            ("квартира с такса меньше 15", {"lte": 15.0}),
            ("квартира с низкая поддержка", {"lte": 12.0}),
        ],
    )
    def test_maintenance(self, query: str, expected: dict) -> None:
        assert _ext.extract_filters(query)["maintenance"] == expected

    def test_no_maintenance_filter(self) -> None:
        assert "maintenance" not in _ext.extract_filters("двукомнатная квартира")


# ---------------------------------------------------------------------------
# Bathrooms
# ---------------------------------------------------------------------------
class TestFilterExtractorBathrooms:
    """Tests for bathrooms filter extraction."""

    @pytest.mark.parametrize(
        ("query", "count"),
        [
            ("квартира с 2 санузла", 2),
            ("квартира один санузл", 1),
            ("квартира два санузла", 2),
            ("квартира три санузла", 3),
        ],
    )
    def test_bathrooms(self, query: str, count: int) -> None:
        assert _ext.extract_filters(query)["bathrooms"] == count

    def test_no_bathrooms_filter(self) -> None:
        assert "bathrooms" not in _ext.extract_filters("двукомнатная квартира")


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------
class TestFilterExtractorCombined:
    """Tests for multiple filters extraction."""

    def test_combined_price_and_rooms(self) -> None:
        result = _ext.extract_filters("двукомнатная квартира до 80000")
        assert result["rooms"] == 2
        assert result["price"] == {"lt": 80000}

    def test_combined_city_and_rooms(self) -> None:
        result = _ext.extract_filters("трехкомнатная квартира в Бургас")
        assert result["rooms"] == 3
        assert result["city"] == "Бургас"

    def test_combined_price_city_furniture(self) -> None:
        result = _ext.extract_filters("квартира в Варна до 100000 с мебелью")
        assert result["city"] == "Варна"
        assert result["price"] == {"lt": 100000}
        assert result["furniture"] == "Есть"

    def test_combined_with_distance_meters(self) -> None:
        result = _ext.extract_filters("квартира в Варна до 500м до моря")
        assert result["city"] == "Варна"
        assert result["distance_to_sea"] == {"lte": 500}

    def test_combined_with_distance_ne_dalshe(self) -> None:
        result = _ext.extract_filters("квартира в Варна не дальше 300м")
        assert result["city"] == "Варна"
        assert result["distance_to_sea"] == {"lte": 300}

    def test_no_filters(self) -> None:
        assert _ext.extract_filters("покажи квартиры") == {}

    def test_empty_query(self) -> None:
        assert _ext.extract_filters("") == {}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------
class TestFilterExtractorEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_price_zero(self) -> None:
        assert "price" not in _ext.extract_filters("квартира до 0")

    def test_rooms_large_number(self) -> None:
        assert _ext.extract_filters("10 комнат")["rooms"] == 10

    def test_unicode_spaces(self) -> None:
        assert _ext.extract_filters("квартира дешевле 100\xa0000")["price"] == {"lt": 100000}

    def test_city_with_digit_rooms(self) -> None:
        result = _ext.extract_filters("3-комнатная квартира в ВАРНА")
        assert result["rooms"] == 3
        assert result["city"] == "Варна"

    def test_multiple_cities_first_in_list_wins(self) -> None:
        result = _ext.extract_filters("квартира в Варна или Бургас")
        assert result["city"] == "Бургас"

    def test_price_lt_pattern_priority(self) -> None:
        assert _ext.extract_filters("квартира до 100000")["price"] == {"lt": 100000}

    def test_partial_word_no_match(self) -> None:
        assert "city" not in _ext.extract_filters("квартира в Вар")

    def test_price_with_text_after(self) -> None:
        result = _ext.extract_filters("квартира дешевле 100000 евро в Бургас")
        assert result["price"] == {"lt": 100000}
        assert result["city"] == "Бургас"

    def test_special_characters_in_query(self) -> None:
        result = _ext.extract_filters("квартира!!! в Варна??? до 50000...")
        assert result["city"] == "Варна"
        assert result["price"] == {"lt": 50000}

    def test_distance_meters_without_sea_context(self) -> None:
        assert "distance_to_sea" not in _ext.extract_filters(
            "квартира 100 метров от центра"
        )

    def test_rooms_digit_in_middle_of_text(self) -> None:
        assert _ext.extract_filters(
            "ищу хорошую 2-комнатную квартиру в Бургасе"
        )["rooms"] == 2

    def test_studiya_case_variations(self) -> None:
        assert _ext.extract_filters("СТУДИЯ в центре города")["rooms"] == 1


# ---------------------------------------------------------------------------
# _parse_number helper
# ---------------------------------------------------------------------------
class TestParseNumberMethod:
    """Tests for the _parse_number helper method."""

    @pytest.mark.parametrize(
        ("input_str", "expected"),
        [
            ("100000", 100000),
            ("100 000", 100000),
            ("100\xa0000", 100000),
            ("100к", 100000),
            ("100 к", 100000),
            ("abc", None),
            ("", None),
        ],
    )
    def test_parse_number(self, input_str: str, expected: int | None) -> None:
        assert _ext._parse_number(input_str) == expected
