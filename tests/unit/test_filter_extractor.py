"""Unit tests for telegram_bot/services/filter_extractor.py."""

from telegram_bot.services.filter_extractor import FilterExtractor


class TestFilterExtractorInit:
    """Test FilterExtractor initialization."""

    def test_can_create_instance(self):
        """Test that FilterExtractor can be instantiated."""
        extractor = FilterExtractor()
        assert extractor is not None


class TestExtractPrice:
    """Test price extraction."""

    def test_extract_price_less_than(self):
        """Test extracting 'less than' price filter."""
        extractor = FilterExtractor()

        queries = [
            ("дешевле 100000", {"lt": 100000}),
            ("до 80000 евро", {"lt": 80000}),
            ("меньше 150000", {"lt": 150000}),
            ("< 120000", {"lt": 120000}),
            ("не дороже 90000", {"lt": 90000}),
        ]

        for query, expected in queries:
            result = extractor._extract_price(query)
            assert result == expected, f"Failed for query: {query}"

    def test_extract_price_greater_than(self):
        """Test extracting 'greater than' price filter."""
        extractor = FilterExtractor()

        queries = [
            ("дороже 100000", {"gt": 100000}),
            ("от 80000", {"gt": 80000}),
            ("больше 50000", {"gt": 50000}),
            ("> 70000", {"gt": 70000}),
        ]

        for query, expected in queries:
            result = extractor._extract_price(query)
            assert result == expected, f"Failed for query: {query}"

    def test_extract_price_range(self):
        """Test extracting price range filter."""
        extractor = FilterExtractor()

        result = extractor._extract_price("от 80000 до 150000 евро")
        assert result == {"gte": 80000, "lte": 150000}

    def test_extract_price_with_k_suffix(self):
        """Test extracting price with 'k' suffix."""
        extractor = FilterExtractor()

        result = extractor._extract_price("до 100к")
        assert result == {"lt": 100000}

    def test_extract_price_with_spaces(self):
        """Test extracting price with space formatting."""
        extractor = FilterExtractor()

        result = extractor._extract_price("дешевле 100 000")
        assert result == {"lt": 100000}

    def test_extract_price_no_price(self):
        """Test query without price returns None."""
        extractor = FilterExtractor()

        result = extractor._extract_price("квартира в Несебр")
        assert result is None


class TestExtractRooms:
    """Test rooms extraction."""

    def test_extract_rooms_digit(self):
        """Test extracting rooms with digit."""
        extractor = FilterExtractor()

        queries = [
            ("3 комнаты", 3),
            ("2-комнатная квартира", 2),
            ("4 комнатная", 4),
        ]

        for query, expected in queries:
            result = extractor._extract_rooms(query)
            assert result == expected, f"Failed for query: {query}"

    def test_extract_rooms_word(self):
        """Test extracting rooms with word."""
        extractor = FilterExtractor()

        queries = [
            ("однокомнатная", 1),
            ("двукомнатная", 2),
            ("трехкомнатная", 3),
            ("четырехкомнатная", 4),
        ]

        for query, expected in queries:
            result = extractor._extract_rooms(query)
            assert result == expected, f"Failed for query: {query}"

    def test_extract_rooms_studio(self):
        """Test extracting studio as 1 room."""
        extractor = FilterExtractor()

        result = extractor._extract_rooms("студия в центре")
        assert result == 1

    def test_extract_rooms_none(self):
        """Test query without rooms returns None."""
        extractor = FilterExtractor()

        result = extractor._extract_rooms("квартира дешевле 100000")
        assert result is None


class TestExtractCity:
    """Test city extraction."""

    def test_extract_known_cities(self):
        """Test extracting known cities."""
        extractor = FilterExtractor()

        cities = [
            ("в Солнечный берег", "Солнечный берег"),
            ("квартиры в Несебр", "Несебр"),
            ("в центре Бургас", "Бургас"),
            ("Варна недорого", "Варна"),
            ("в Поморие", "Поморие"),
            ("Созополь", "Созополь"),
        ]

        for query, expected in cities:
            result = extractor._extract_city(query)
            assert result == expected, f"Failed for query: {query}"

    def test_extract_city_case_insensitive(self):
        """Test that city extraction is case insensitive."""
        extractor = FilterExtractor()

        result = extractor._extract_city("в НЕСЕБР")
        assert result == "Несебр"

    def test_extract_city_none(self):
        """Test query without known city returns None."""
        extractor = FilterExtractor()

        result = extractor._extract_city("квартира дешевле 100000")
        assert result is None


class TestExtractArea:
    """Test area extraction."""

    def test_extract_area_greater_than(self):
        """Test extracting 'greater than' area filter."""
        extractor = FilterExtractor()

        queries = [
            ("больше 50 м2", {"gte": 50}),
            ("от 60 кв.м", {"gte": 60}),
        ]

        for query, expected in queries:
            result = extractor._extract_area(query)
            assert result == expected, f"Failed for query: {query}"

    def test_extract_area_less_than(self):
        """Test extracting 'less than' area filter."""
        extractor = FilterExtractor()

        queries = [
            ("меньше 100 м2", {"lte": 100}),
            ("до 80 кв.м", {"lte": 80}),
        ]

        for query, expected in queries:
            result = extractor._extract_area(query)
            assert result == expected, f"Failed for query: {query}"


class TestExtractFloor:
    """Test floor extraction."""

    def test_extract_floor(self):
        """Test extracting floor number."""
        extractor = FilterExtractor()

        queries = [
            ("4 этаж", 4),
            ("на 3 этаже", 3),
            ("5 этаж", 5),
        ]

        for query, expected in queries:
            result = extractor._extract_floor(query)
            assert result == expected, f"Failed for query: {query}"


class TestExtractDistanceToSea:
    """Test distance to sea extraction."""

    def test_extract_distance_meters(self):
        """Test extracting distance in meters."""
        extractor = FilterExtractor()

        queries = [
            ("до 500м до моря", {"lte": 500}),
            ("не дальше 600 метров", {"lte": 600}),
            ("в 400м от моря", {"lte": 400}),
        ]

        for query, expected in queries:
            result = extractor._extract_distance_to_sea(query)
            assert result == expected, f"Failed for query: {query}"

    def test_extract_distance_first_line(self):
        """Test extracting 'first line' as close distance."""
        extractor = FilterExtractor()

        result = extractor._extract_distance_to_sea("первая линия")
        assert result == {"lte": 200}

    def test_extract_distance_near_sea(self):
        """Test extracting 'near sea' as close distance."""
        extractor = FilterExtractor()

        result = extractor._extract_distance_to_sea("у моря")
        assert result == {"lte": 200}


class TestExtractMaintenance:
    """Test maintenance cost extraction."""

    def test_extract_maintenance_specific(self):
        """Test extracting specific maintenance cost."""
        extractor = FilterExtractor()

        result = extractor._extract_maintenance("поддержка до 10 евро")
        assert result == {"lte": 10.0}

    def test_extract_maintenance_low(self):
        """Test extracting 'low maintenance' as default value."""
        extractor = FilterExtractor()

        result = extractor._extract_maintenance("низкая поддержка")
        assert result == {"lte": 12.0}


class TestExtractBathrooms:
    """Test bathrooms extraction."""

    def test_extract_bathrooms_digit(self):
        """Test extracting bathrooms with digit."""
        extractor = FilterExtractor()

        result = extractor._extract_bathrooms("2 санузла")
        assert result == 2

    def test_extract_bathrooms_word(self):
        """Test extracting bathrooms with word."""
        extractor = FilterExtractor()

        queries = [
            ("один санузел", 1),
            ("два санузла", 2),
            ("три санузла", 3),
        ]

        for query, expected in queries:
            result = extractor._extract_bathrooms(query)
            assert result == expected, f"Failed for query: {query}"


class TestExtractFurniture:
    """Test furniture extraction."""

    def test_extract_furniture_present(self):
        """Test extracting furniture requirement."""
        extractor = FilterExtractor()

        queries = [
            "с мебелью",
            "меблированная квартира",
            "обставленная",
        ]

        for query in queries:
            result = extractor._extract_furniture(query)
            assert result == "Есть", f"Failed for query: {query}"

    def test_extract_furniture_not_mentioned(self):
        """Test query without furniture returns None."""
        extractor = FilterExtractor()

        result = extractor._extract_furniture("квартира в Несебр")
        assert result is None


class TestExtractYearRound:
    """Test year-round extraction."""

    def test_extract_year_round_present(self):
        """Test extracting year-round requirement."""
        extractor = FilterExtractor()

        queries = [
            "круглогодичная",
            "круглый год",
            "зимой можно жить",
        ]

        for query in queries:
            result = extractor._extract_year_round(query)
            assert result == "Да", f"Failed for query: {query}"


class TestExtractFilters:
    """Test full filter extraction."""

    def test_extract_all_filters(self):
        """Test extracting all filters from complex query."""
        extractor = FilterExtractor()

        query = "2-комнатная в Солнечный берег дешевле 100000 до 500м от моря"
        result = extractor.extract_filters(query)

        assert result["rooms"] == 2
        assert result["city"] == "Солнечный берег"
        assert result["price"] == {"lt": 100000}
        assert result["distance_to_sea"] == {"lte": 500}

    def test_extract_filters_empty(self):
        """Test query with no extractable filters."""
        extractor = FilterExtractor()

        result = extractor.extract_filters("покажи что-нибудь интересное")

        assert result == {}

    def test_extract_filters_partial(self):
        """Test query with some filters."""
        extractor = FilterExtractor()

        result = extractor.extract_filters("студия в Варна")

        assert result["rooms"] == 1
        assert result["city"] == "Варна"
        assert "price" not in result


class TestParseNumber:
    """Test number parsing helper."""

    def test_parse_simple_number(self):
        """Test parsing simple number."""
        extractor = FilterExtractor()

        assert extractor._parse_number("100000") == 100000

    def test_parse_number_with_spaces(self):
        """Test parsing number with spaces."""
        extractor = FilterExtractor()

        assert extractor._parse_number("100 000") == 100000

    def test_parse_number_with_k_suffix(self):
        """Test parsing number with k suffix."""
        extractor = FilterExtractor()

        assert extractor._parse_number("100к") == 100000

    def test_parse_invalid_number(self):
        """Test parsing invalid number returns None."""
        extractor = FilterExtractor()

        assert extractor._parse_number("abc") is None
