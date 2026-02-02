"""Tests for QueryPreprocessor."""

from telegram_bot.services.query_preprocessor import QueryPreprocessor


class TestQueryPreprocessorTranslit:
    """Tests for transliteration normalization."""

    def test_normalize_burgas(self):
        """Test Burgas transliteration."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("apartments in Burgas")
        assert "Бургас" in result

    def test_normalize_sunny_beach(self):
        """Test Sunny Beach transliteration."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("Sunny Beach apartments")
        assert "Солнечный берег" in result

    def test_normalize_sveti_vlas(self):
        """Test Sveti Vlas transliteration."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("villa in Sveti Vlas")
        assert "Святой Влас" in result

    def test_normalize_preserves_cyrillic(self):
        """Test cyrillic text is preserved."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("квартиры в Бургасе")
        assert result == "квартиры в Бургасе"

    def test_normalize_case_insensitive(self):
        """Test case insensitive matching."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("BURGAS apartment")
        assert "Бургас" in result


class TestQueryPreprocessorRRFWeights:
    """Tests for dynamic RRF weight calculation."""

    def test_default_weights_for_general_query(self):
        """Test default RRF weights for general queries."""
        preprocessor = QueryPreprocessor()
        dense, sparse = preprocessor.get_rrf_weights("квартиры у моря")
        assert dense == 0.6
        assert sparse == 0.4

    def test_sparse_favored_for_id_query(self):
        """Test RRF weights favor sparse for ID queries."""
        preprocessor = QueryPreprocessor()
        dense, sparse = preprocessor.get_rrf_weights("квартира ID 12345")
        assert dense == 0.2
        assert sparse == 0.8

    def test_sparse_favored_for_corpus_query(self):
        """Test RRF weights favor sparse for corpus/block queries."""
        preprocessor = QueryPreprocessor()
        dense, sparse = preprocessor.get_rrf_weights("ЖК Елените корпус 5")
        assert dense == 0.2
        assert sparse == 0.8

    def test_sparse_favored_for_floor_query(self):
        """Test RRF weights favor sparse for floor queries."""
        preprocessor = QueryPreprocessor()
        dense, sparse = preprocessor.get_rrf_weights("квартира этаж 3")
        assert dense == 0.2
        assert sparse == 0.8


class TestQueryPreprocessorCacheThreshold:
    """Tests for adaptive cache threshold."""

    def test_default_threshold(self):
        """Test default cache threshold."""
        preprocessor = QueryPreprocessor()
        threshold = preprocessor.get_cache_threshold("квартиры в центре")
        assert threshold == 0.10

    def test_strict_threshold_for_numbers(self):
        """Test strict threshold for queries with numbers."""
        preprocessor = QueryPreprocessor()
        threshold = preprocessor.get_cache_threshold("цена квартиры 12345")
        assert threshold == 0.05

    def test_strict_threshold_for_corpus(self):
        """Test strict threshold for corpus queries."""
        preprocessor = QueryPreprocessor()
        threshold = preprocessor.get_cache_threshold("корпус А цена")
        assert threshold == 0.05


class TestQueryPreprocessorAnalyze:
    """Tests for full analysis."""

    def test_analyze_returns_all_fields(self):
        """Test analyze returns complete dict."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.analyze("apartments in Burgas ID 123")

        assert "original_query" in result
        assert "normalized_query" in result
        assert "rrf_weights" in result
        assert "cache_threshold" in result
        assert "is_exact" in result

    def test_analyze_combines_translit_and_weights(self):
        """Test analyze applies both translit and weight calculation."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.analyze("Sunny Beach корпус 5")

        assert "Солнечный берег" in result["normalized_query"]
        assert result["rrf_weights"]["sparse"] == 0.8
        assert result["is_exact"] is True


class TestQueryPreprocessorHasExactIdentifier:
    """Tests for exact identifier detection."""

    def test_detects_id_pattern(self):
        """Test detects ID pattern."""
        preprocessor = QueryPreprocessor()
        assert preprocessor.has_exact_identifier("квартира ID 12345") is True

    def test_detects_long_number(self):
        """Test detects long numbers (IDs)."""
        preprocessor = QueryPreprocessor()
        assert preprocessor.has_exact_identifier("объект 123456") is True

    def test_detects_corpus_number(self):
        """Test detects корпус with number."""
        preprocessor = QueryPreprocessor()
        assert preprocessor.has_exact_identifier("корпус 5") is True

    def test_detects_corpus_letter(self):
        """Test detects корпус with letter."""
        preprocessor = QueryPreprocessor()
        assert preprocessor.has_exact_identifier("корпус А") is True

    def test_detects_block(self):
        """Test detects блок pattern."""
        preprocessor = QueryPreprocessor()
        assert preprocessor.has_exact_identifier("блок B") is True

    def test_detects_section(self):
        """Test detects секция pattern."""
        preprocessor = QueryPreprocessor()
        assert preprocessor.has_exact_identifier("секция 2") is True

    def test_detects_floor(self):
        """Test detects этаж pattern."""
        preprocessor = QueryPreprocessor()
        assert preprocessor.has_exact_identifier("этаж 5") is True

    def test_detects_zhk(self):
        """Test detects ЖК pattern."""
        preprocessor = QueryPreprocessor()
        assert preprocessor.has_exact_identifier("ЖК Елените") is True

    def test_returns_false_for_semantic_query(self):
        """Test returns False for semantic queries."""
        preprocessor = QueryPreprocessor()
        assert preprocessor.has_exact_identifier("красивая квартира у моря") is False


class TestQueryPreprocessorTranslitAdditional:
    """Additional transliteration tests."""

    def test_normalize_multiple_cities(self):
        """Test multiple cities in one query."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("apartments in Burgas or Varna")
        assert "Бургас" in result
        assert "Варна" in result

    def test_normalize_golden_sands(self):
        """Test Golden Sands transliteration."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("Golden Sands hotel")
        assert "Золотые пески" in result

    def test_normalize_nessebar_variant(self):
        """Test Nessebar spelling variant."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.normalize_translit("Nessebar old town")
        assert "Несебър" in result
