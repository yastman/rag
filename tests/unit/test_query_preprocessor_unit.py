"""Unit tests for telegram_bot/services/query_preprocessor.py."""

import pytest

from telegram_bot.services.query_preprocessor import QueryPreprocessor


class TestQueryPreprocessorInit:
    """Test QueryPreprocessor initialization."""

    def test_init_creates_translit_map(self):
        """Test that translit map is initialized."""
        pp = QueryPreprocessor()

        assert hasattr(pp, "TRANSLIT_MAP")
        assert len(pp.TRANSLIT_MAP) > 0
        assert "Varna" in pp.TRANSLIT_MAP

    def test_init_creates_exact_patterns(self):
        """Test that exact patterns are initialized."""
        pp = QueryPreprocessor()

        assert hasattr(pp, "EXACT_PATTERNS")
        assert len(pp.EXACT_PATTERNS) > 0


class TestNormalizeTranslit:
    """Test transliteration normalization."""

    def test_translit_varna(self):
        """Test Varna transliteration."""
        pp = QueryPreprocessor()
        result = pp.normalize_translit("apartments in Varna")

        assert "Варна" in result
        assert "Varna" not in result

    def test_translit_nesebar(self):
        """Test Nesebar transliteration (both spellings)."""
        pp = QueryPreprocessor()

        result1 = pp.normalize_translit("hotels in Nesebar")
        result2 = pp.normalize_translit("hotels in Nessebar")

        assert "Несебър" in result1
        assert "Несебър" in result2

    def test_translit_sunny_beach(self):
        """Test Sunny Beach transliteration."""
        pp = QueryPreprocessor()
        result = pp.normalize_translit("apartments in Sunny Beach")

        assert "Солнечный берег" in result

    def test_translit_case_insensitive(self):
        """Test case-insensitive transliteration."""
        pp = QueryPreprocessor()

        result_lower = pp.normalize_translit("varna")
        result_upper = pp.normalize_translit("VARNA")
        result_mixed = pp.normalize_translit("Varna")

        assert "Варна" in result_lower
        assert "Варна" in result_upper
        assert "Варна" in result_mixed

    def test_translit_multiple_cities(self):
        """Test transliteration of multiple cities in one query."""
        pp = QueryPreprocessor()
        result = pp.normalize_translit("apartments in Varna or Burgas")

        assert "Варна" in result
        assert "Бургас" in result
        assert "Varna" not in result
        assert "Burgas" not in result

    def test_translit_no_match(self):
        """Test that unknown words are not changed."""
        pp = QueryPreprocessor()
        query = "apartments in Moscow"
        result = pp.normalize_translit(query)

        assert result == query

    def test_translit_preserves_other_text(self):
        """Test that non-transliterable text is preserved."""
        pp = QueryPreprocessor()
        result = pp.normalize_translit("2-room apartments in Varna under 50000 EUR")

        assert "Варна" in result
        assert "2-room" in result
        assert "50000 EUR" in result

    def test_translit_sveti_vlas_variants(self):
        """Test Sveti Vlas transliteration variants."""
        pp = QueryPreprocessor()

        result1 = pp.normalize_translit("Sveti Vlas")
        result2 = pp.normalize_translit("Svyati Vlas")
        result3 = pp.normalize_translit("St Vlas")

        assert "Святой Влас" in result1
        assert "Святой Влас" in result2
        assert "Святой Влас" in result3


class TestGetRRFWeights:
    """Test RRF weight calculation."""

    def test_semantic_query_weights(self):
        """Test weights for semantic queries."""
        pp = QueryPreprocessor()
        dense, sparse = pp.get_rrf_weights("квартиры у моря недорого")

        assert dense == 0.6
        assert sparse == 0.4

    def test_exact_query_with_id(self):
        """Test weights for queries with ID."""
        pp = QueryPreprocessor()
        dense, sparse = pp.get_rrf_weights("показать ID 12345")

        assert dense == 0.2
        assert sparse == 0.8

    def test_exact_query_with_long_number(self):
        """Test weights for queries with long numbers."""
        pp = QueryPreprocessor()
        dense, sparse = pp.get_rrf_weights("объект 123456")

        assert dense == 0.2
        assert sparse == 0.8

    def test_exact_query_with_corpus(self):
        """Test weights for queries with corpus number."""
        pp = QueryPreprocessor()
        dense, sparse = pp.get_rrf_weights("квартира корпус 5")

        assert dense == 0.2
        assert sparse == 0.8

    def test_exact_query_with_block(self):
        """Test weights for queries with block number."""
        pp = QueryPreprocessor()
        dense, sparse = pp.get_rrf_weights("блок 3 этаж 2")

        assert dense == 0.2
        assert sparse == 0.8

    def test_exact_query_with_floor(self):
        """Test weights for queries with floor number."""
        pp = QueryPreprocessor()
        dense, sparse = pp.get_rrf_weights("этаж 5 вид на море")

        assert dense == 0.2
        assert sparse == 0.8

    def test_exact_query_with_zhk(self):
        """Test weights for queries with ЖК (residential complex)."""
        pp = QueryPreprocessor()
        dense, sparse = pp.get_rrf_weights("ЖК Елените апартаменты")

        assert dense == 0.2
        assert sparse == 0.8

    def test_weights_sum_to_one(self):
        """Test that weights always sum to 1.0."""
        pp = QueryPreprocessor()

        queries = [
            "semantic query",
            "ID 12345",
            "корпус 5",
            "блок А этаж 3",
        ]

        for query in queries:
            dense, sparse = pp.get_rrf_weights(query)
            assert dense + sparse == pytest.approx(1.0)


class TestGetCacheThreshold:
    """Test cache threshold calculation."""

    def test_semantic_query_threshold(self):
        """Test threshold for semantic queries."""
        pp = QueryPreprocessor()
        threshold = pp.get_cache_threshold("квартиры с видом на море")

        assert threshold == 0.10

    def test_strict_threshold_with_numbers(self):
        """Test strict threshold for queries with numbers."""
        pp = QueryPreprocessor()
        threshold = pp.get_cache_threshold("квартира 123")

        assert threshold == 0.05

    def test_strict_threshold_with_corpus(self):
        """Test strict threshold for queries with corpus."""
        pp = QueryPreprocessor()
        threshold = pp.get_cache_threshold("корпус А")

        assert threshold == 0.05

    def test_strict_threshold_with_block(self):
        """Test strict threshold for queries with block."""
        pp = QueryPreprocessor()
        threshold = pp.get_cache_threshold("блок 3")

        assert threshold == 0.05

    def test_strict_threshold_with_floor(self):
        """Test strict threshold for queries with floor."""
        pp = QueryPreprocessor()
        threshold = pp.get_cache_threshold("этаж 5")

        assert threshold == 0.05

    def test_strict_threshold_with_id(self):
        """Test strict threshold for queries with ID."""
        pp = QueryPreprocessor()
        threshold = pp.get_cache_threshold("ID квартиры")

        assert threshold == 0.05


class TestHasExactIdentifier:
    """Test exact identifier detection."""

    def test_no_identifier(self):
        """Test query without identifiers."""
        pp = QueryPreprocessor()
        assert pp.has_exact_identifier("квартиры у моря") is False

    def test_has_id(self):
        """Test query with ID."""
        pp = QueryPreprocessor()
        assert pp.has_exact_identifier("ID 12345") is True

    def test_has_long_number(self):
        """Test query with long number."""
        pp = QueryPreprocessor()
        assert pp.has_exact_identifier("объект 123456") is True

    def test_has_corpus(self):
        """Test query with corpus."""
        pp = QueryPreprocessor()
        assert pp.has_exact_identifier("корпус 5") is True
        assert pp.has_exact_identifier("корпус A") is True

    def test_has_block(self):
        """Test query with block."""
        pp = QueryPreprocessor()
        assert pp.has_exact_identifier("блок 3") is True
        assert pp.has_exact_identifier("блок B") is True

    def test_has_section(self):
        """Test query with section."""
        pp = QueryPreprocessor()
        assert pp.has_exact_identifier("секция 2") is True

    def test_has_floor(self):
        """Test query with floor."""
        pp = QueryPreprocessor()
        assert pp.has_exact_identifier("этаж 5") is True

    def test_has_zhk(self):
        """Test query with ЖК."""
        pp = QueryPreprocessor()
        assert pp.has_exact_identifier("ЖК Елените") is True


class TestAnalyze:
    """Test full analysis pipeline."""

    def test_analyze_semantic_query(self):
        """Test analysis of semantic query."""
        pp = QueryPreprocessor()
        result = pp.analyze("квартиры в Varna недорого")

        assert result["original_query"] == "квартиры в Varna недорого"
        assert "Варна" in result["normalized_query"]
        assert result["rrf_weights"]["dense"] == 0.6
        assert result["rrf_weights"]["sparse"] == 0.4
        assert result["cache_threshold"] == 0.10
        assert result["is_exact"] is False

    def test_analyze_exact_query(self):
        """Test analysis of exact query."""
        pp = QueryPreprocessor()
        result = pp.analyze("квартира ID 12345 корпус 3")

        assert result["original_query"] == "квартира ID 12345 корпус 3"
        assert result["rrf_weights"]["dense"] == 0.2
        assert result["rrf_weights"]["sparse"] == 0.8
        assert result["cache_threshold"] == 0.05
        assert result["is_exact"] is True

    def test_analyze_mixed_query(self):
        """Test analysis with transliteration and identifiers."""
        pp = QueryPreprocessor()
        result = pp.analyze("apartments in Sunny Beach корпус 5")

        assert "Солнечный берег" in result["normalized_query"]
        assert result["is_exact"] is True
        assert result["rrf_weights"]["sparse"] == 0.8

    def test_analyze_returns_all_keys(self):
        """Test that analyze returns all expected keys."""
        pp = QueryPreprocessor()
        result = pp.analyze("test query")

        expected_keys = [
            "original_query",
            "normalized_query",
            "rrf_weights",
            "cache_threshold",
            "is_exact",
        ]

        for key in expected_keys:
            assert key in result

    def test_analyze_rrf_weights_structure(self):
        """Test that rrf_weights has correct structure."""
        pp = QueryPreprocessor()
        result = pp.analyze("test query")

        assert "dense" in result["rrf_weights"]
        assert "sparse" in result["rrf_weights"]
        assert isinstance(result["rrf_weights"]["dense"], float)
        assert isinstance(result["rrf_weights"]["sparse"], float)
