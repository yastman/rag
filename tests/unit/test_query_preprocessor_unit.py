"""Unit tests for telegram_bot/services/query_preprocessor.py."""

import pytest

from telegram_bot.services.query_preprocessor import QueryPreprocessor


_pp = QueryPreprocessor()


class TestQueryPreprocessorInit:
    """Test QueryPreprocessor initialization."""

    def test_init_creates_translit_map(self):
        assert hasattr(_pp, "TRANSLIT_MAP")
        assert len(_pp.TRANSLIT_MAP) > 0
        assert "Varna" in _pp.TRANSLIT_MAP

    def test_init_creates_exact_patterns(self):
        assert hasattr(_pp, "EXACT_PATTERNS")
        assert len(_pp.EXACT_PATTERNS) > 0


class TestNormalizeTranslit:
    """Test transliteration normalization."""

    @pytest.mark.parametrize(
        ("query", "expected_in_result"),
        [
            ("apartments in Varna", "Варна"),
            ("apartments in Sunny Beach", "Солнечный берег"),
            ("varna", "Варна"),
            ("VARNA", "Варна"),
            ("Varna", "Варна"),
            ("Sveti Vlas", "Святой Влас"),
            ("Svyati Vlas", "Святой Влас"),
            ("St Vlas", "Святой Влас"),
        ],
    )
    def test_translit_produces_expected(self, query, expected_in_result):
        assert expected_in_result in _pp.normalize_translit(query)

    @pytest.mark.parametrize(
        ("query", "expected_in_result"),
        [
            ("hotels in Nesebar", "Несебър"),
            ("hotels in Nessebar", "Несебър"),
        ],
    )
    def test_translit_nesebar_variants(self, query, expected_in_result):
        assert expected_in_result in _pp.normalize_translit(query)

    def test_translit_multiple_cities(self):
        result = _pp.normalize_translit("apartments in Varna or Burgas")
        assert "Варна" in result
        assert "Бургас" in result
        assert "Varna" not in result
        assert "Burgas" not in result

    def test_translit_no_match(self):
        query = "apartments in Moscow"
        assert _pp.normalize_translit(query) == query

    def test_translit_preserves_other_text(self):
        result = _pp.normalize_translit("2-room apartments in Varna under 50000 EUR")
        assert "Варна" in result
        assert "2-room" in result
        assert "50000 EUR" in result


class TestGetRRFWeights:
    """Test RRF weight calculation."""

    @pytest.mark.parametrize(
        ("query", "expected_dense", "expected_sparse"),
        [
            pytest.param("квартиры у моря недорого", 0.6, 0.4, id="semantic"),
            pytest.param("показать ID 12345", 0.2, 0.8, id="id"),
            pytest.param("объект 123456", 0.2, 0.8, id="long_number"),
            pytest.param("квартира корпус 5", 0.2, 0.8, id="corpus"),
            pytest.param("блок 3 этаж 2", 0.2, 0.8, id="block"),
            pytest.param("этаж 5 вид на море", 0.2, 0.8, id="floor"),
            pytest.param("ЖК Елените апартаменты", 0.2, 0.8, id="zhk"),
        ],
    )
    def test_rrf_weights(self, query, expected_dense, expected_sparse):
        dense, sparse = _pp.get_rrf_weights(query)
        assert dense == expected_dense
        assert sparse == expected_sparse

    @pytest.mark.parametrize(
        "query",
        ["semantic query", "ID 12345", "корпус 5", "блок А этаж 3"],
    )
    def test_weights_sum_to_one(self, query):
        dense, sparse = _pp.get_rrf_weights(query)
        assert dense + sparse == pytest.approx(1.0)


class TestGetCacheThreshold:
    """Test cache threshold calculation."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            pytest.param("квартиры с видом на море", 0.10, id="semantic"),
            pytest.param("квартира 123", 0.05, id="numbers"),
            pytest.param("корпус А", 0.05, id="corpus"),
            pytest.param("блок 3", 0.05, id="block"),
            pytest.param("этаж 5", 0.05, id="floor"),
            pytest.param("ID квартиры", 0.05, id="id"),
        ],
    )
    def test_cache_threshold(self, query, expected):
        assert _pp.get_cache_threshold(query) == expected


class TestHasExactIdentifier:
    """Test exact identifier detection."""

    @pytest.mark.parametrize(
        "query",
        [
            pytest.param("ID 12345", id="id"),
            pytest.param("объект 123456", id="long_number"),
            pytest.param("корпус 5", id="corpus_num"),
            pytest.param("корпус A", id="corpus_letter"),
            pytest.param("блок 3", id="block_num"),
            pytest.param("блок B", id="block_letter"),
            pytest.param("секция 2", id="section"),
            pytest.param("этаж 5", id="floor"),
            pytest.param("ЖК Елените", id="zhk"),
        ],
    )
    def test_has_exact_identifier(self, query):
        assert _pp.has_exact_identifier(query) is True

    def test_no_identifier(self):
        assert _pp.has_exact_identifier("квартиры у моря") is False


class TestAnalyze:
    """Test full analysis pipeline."""

    def test_analyze_semantic_query(self):
        result = _pp.analyze("квартиры в Varna недорого")
        assert result["original_query"] == "квартиры в Varna недорого"
        assert "Варна" in result["normalized_query"]
        assert result["rrf_weights"]["dense"] == 0.6
        assert result["rrf_weights"]["sparse"] == 0.4
        assert result["cache_threshold"] == 0.10
        assert result["is_exact"] is False

    def test_analyze_exact_query(self):
        result = _pp.analyze("квартира ID 12345 корпус 3")
        assert result["original_query"] == "квартира ID 12345 корпус 3"
        assert result["rrf_weights"]["dense"] == 0.2
        assert result["rrf_weights"]["sparse"] == 0.8
        assert result["cache_threshold"] == 0.05
        assert result["is_exact"] is True

    def test_analyze_mixed_query(self):
        result = _pp.analyze("apartments in Sunny Beach корпус 5")
        assert "Солнечный берег" in result["normalized_query"]
        assert result["is_exact"] is True
        assert result["rrf_weights"]["sparse"] == 0.8

    def test_analyze_returns_all_keys(self):
        result = _pp.analyze("test query")
        for key in ["original_query", "normalized_query", "rrf_weights", "cache_threshold", "is_exact"]:
            assert key in result

    def test_analyze_rrf_weights_structure(self):
        result = _pp.analyze("test query")
        assert "dense" in result["rrf_weights"]
        assert "sparse" in result["rrf_weights"]
        assert isinstance(result["rrf_weights"]["dense"], float)
        assert isinstance(result["rrf_weights"]["sparse"], float)
