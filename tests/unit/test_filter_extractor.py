"""Unit tests for telegram_bot/services/filter_extractor.py."""

import pytest

from telegram_bot.services.filter_extractor import FilterExtractor


# Read-only: safe to share across all tests.
_extractor = FilterExtractor()


class TestFilterExtractorInit:
    """Test FilterExtractor initialization."""

    def test_can_create_instance(self):
        assert _extractor is not None


class TestExtractPrice:
    """Test price extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("дешевле 100000", {"lt": 100000}),
            ("до 80000 евро", {"lt": 80000}),
            ("меньше 150000", {"lt": 150000}),
            ("< 120000", {"lt": 120000}),
            ("не дороже 90000", {"lt": 90000}),
        ],
    )
    def test_extract_price_less_than(self, query, expected):
        assert _extractor._extract_price(query) == expected

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("дороже 100000", {"gt": 100000}),
            ("от 80000", {"gt": 80000}),
            ("больше 50000", {"gt": 50000}),
            ("> 70000", {"gt": 70000}),
        ],
    )
    def test_extract_price_greater_than(self, query, expected):
        assert _extractor._extract_price(query) == expected

    def test_extract_price_range(self):
        assert _extractor._extract_price("от 80000 до 150000 евро") == {
            "gte": 80000,
            "lte": 150000,
        }

    def test_extract_price_with_k_suffix(self):
        assert _extractor._extract_price("до 100к") == {"lt": 100000}

    def test_extract_price_with_spaces(self):
        assert _extractor._extract_price("дешевле 100 000") == {"lt": 100000}

    def test_extract_price_no_price(self):
        assert _extractor._extract_price("квартира в Несебр") is None


class TestExtractRooms:
    """Test rooms extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("3 комнаты", 3),
            ("2-комнатная квартира", 2),
            ("4 комнатная", 4),
        ],
    )
    def test_extract_rooms_digit(self, query, expected):
        assert _extractor._extract_rooms(query) == expected

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("однокомнатная", 1),
            ("двукомнатная", 2),
            ("трехкомнатная", 3),
            ("четырехкомнатная", 4),
        ],
    )
    def test_extract_rooms_word(self, query, expected):
        assert _extractor._extract_rooms(query) == expected

    def test_extract_rooms_studio(self):
        assert _extractor._extract_rooms("студия в центре") == 1

    def test_extract_rooms_none(self):
        assert _extractor._extract_rooms("квартира дешевле 100000") is None


class TestExtractCity:
    """Test city extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("в Солнечный берег", "Солнечный берег"),
            ("квартиры в Несебр", "Несебр"),
            ("в центре Бургас", "Бургас"),
            ("Варна недорого", "Варна"),
            ("в Поморие", "Поморие"),
            ("Созополь", "Созополь"),
        ],
    )
    def test_extract_known_cities(self, query, expected):
        assert _extractor._extract_city(query) == expected

    def test_extract_city_case_insensitive(self):
        assert _extractor._extract_city("в НЕСЕБР") == "Несебр"

    def test_extract_city_none(self):
        assert _extractor._extract_city("квартира дешевле 100000") is None


class TestExtractArea:
    """Test area extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("больше 50 м2", {"gte": 50}),
            ("от 60 кв.м", {"gte": 60}),
        ],
    )
    def test_extract_area_greater_than(self, query, expected):
        assert _extractor._extract_area(query) == expected

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("меньше 100 м2", {"lte": 100}),
            ("до 80 кв.м", {"lte": 80}),
        ],
    )
    def test_extract_area_less_than(self, query, expected):
        assert _extractor._extract_area(query) == expected


class TestExtractFloor:
    """Test floor extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("4 этаж", 4),
            ("на 3 этаже", 3),
            ("5 этаж", 5),
        ],
    )
    def test_extract_floor(self, query, expected):
        assert _extractor._extract_floor(query) == expected


class TestExtractDistanceToSea:
    """Test distance to sea extraction."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("до 500м до моря", {"lte": 500}),
            ("не дальше 600 метров", {"lte": 600}),
            ("в 400м от моря", {"lte": 400}),
        ],
    )
    def test_extract_distance_meters(self, query, expected):
        assert _extractor._extract_distance_to_sea(query) == expected

    def test_extract_distance_first_line(self):
        assert _extractor._extract_distance_to_sea("первая линия") == {"lte": 200}

    def test_extract_distance_near_sea(self):
        assert _extractor._extract_distance_to_sea("у моря") == {"lte": 200}


class TestExtractMaintenance:
    """Test maintenance cost extraction."""

    def test_extract_maintenance_specific(self):
        assert _extractor._extract_maintenance("поддержка до 10 евро") == {"lte": 10.0}

    def test_extract_maintenance_low(self):
        assert _extractor._extract_maintenance("низкая поддержка") == {"lte": 12.0}


class TestExtractBathrooms:
    """Test bathrooms extraction."""

    def test_extract_bathrooms_digit(self):
        assert _extractor._extract_bathrooms("2 санузла") == 2

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            ("один санузел", 1),
            ("два санузла", 2),
            ("три санузла", 3),
        ],
    )
    def test_extract_bathrooms_word(self, query, expected):
        assert _extractor._extract_bathrooms(query) == expected


class TestExtractFurniture:
    """Test furniture extraction."""

    @pytest.mark.parametrize(
        "query",
        ["с мебелью", "меблированная квартира", "обставленная"],
    )
    def test_extract_furniture_present(self, query):
        assert _extractor._extract_furniture(query) == "Есть"

    def test_extract_furniture_not_mentioned(self):
        assert _extractor._extract_furniture("квартира в Несебр") is None


class TestExtractYearRound:
    """Test year-round extraction."""

    @pytest.mark.parametrize(
        "query",
        ["круглогодичная", "круглый год", "зимой можно жить"],
    )
    def test_extract_year_round_present(self, query):
        assert _extractor._extract_year_round(query) == "Да"


class TestExtractFilters:
    """Test full filter extraction."""

    def test_extract_all_filters(self):
        result = _extractor.extract_filters(
            "2-комнатная в Солнечный берег дешевле 100000 до 500м от моря"
        )
        assert result["rooms"] == 2
        assert result["city"] == "Солнечный берег"
        assert result["price"] == {"lt": 100000}
        assert result["distance_to_sea"] == {"lte": 500}

    def test_extract_filters_empty(self):
        assert _extractor.extract_filters("покажи что-нибудь интересное") == {}

    def test_extract_filters_partial(self):
        result = _extractor.extract_filters("студия в Варна")
        assert result["rooms"] == 1
        assert result["city"] == "Варна"
        assert "price" not in result


class TestParseNumber:
    """Test number parsing helper."""

    @pytest.mark.parametrize(
        ("input_str", "expected"),
        [
            ("100000", 100000),
            ("100 000", 100000),
            ("100к", 100000),
            ("abc", None),
        ],
    )
    def test_parse_number(self, input_str, expected):
        assert _extractor._parse_number(input_str) == expected
