"""Tests for QueryPreprocessor."""

import pytest

from telegram_bot.services.query_preprocessor import QueryPreprocessor


_preprocessor = QueryPreprocessor()


class TestQueryPreprocessorTranslit:
    """Tests for transliteration normalization."""

    @pytest.mark.parametrize(
        ("query", "expected_in_result"),
        [
            ("apartments in Burgas", "Бургас"),
            ("Sunny Beach apartments", "Солнечный берег"),
            ("villa in Sveti Vlas", "Святой Влас"),
            ("BURGAS apartment", "Бургас"),
            ("Golden Sands hotel", "Золотые пески"),
            ("Nessebar old town", "Несебър"),
        ],
    )
    def test_normalize_translit(self, query, expected_in_result):
        result = _preprocessor.normalize_translit(query)
        assert expected_in_result in result

    def test_normalize_preserves_cyrillic(self):
        result = _preprocessor.normalize_translit("квартиры в Бургасе")
        assert result == "квартиры в Бургасе"

    def test_normalize_multiple_cities(self):
        result = _preprocessor.normalize_translit("apartments in Burgas or Varna")
        assert "Бургас" in result
        assert "Варна" in result


class TestQueryPreprocessorRRFWeights:
    """Tests for dynamic RRF weight calculation."""

    @pytest.mark.parametrize(
        ("query", "expected_dense", "expected_sparse"),
        [
            pytest.param("квартиры у моря", 0.6, 0.4, id="general"),
            pytest.param("квартира ID 12345", 0.2, 0.8, id="id_query"),
            pytest.param("ЖК Елените корпус 5", 0.2, 0.8, id="corpus_query"),
            pytest.param("квартира этаж 3", 0.2, 0.8, id="floor_query"),
        ],
    )
    def test_rrf_weights(self, query, expected_dense, expected_sparse):
        dense, sparse = _preprocessor.get_rrf_weights(query)
        assert dense == expected_dense
        assert sparse == expected_sparse


class TestQueryPreprocessorCacheThreshold:
    """Tests for adaptive cache threshold."""

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            pytest.param("квартиры в центре", 0.10, id="default"),
            pytest.param("цена квартиры 12345", 0.05, id="numbers"),
            pytest.param("корпус А цена", 0.05, id="corpus"),
        ],
    )
    def test_cache_threshold(self, query, expected):
        assert _preprocessor.get_cache_threshold(query) == expected


class TestQueryPreprocessorAnalyze:
    """Tests for full analysis."""

    def test_analyze_returns_all_fields(self):
        result = _preprocessor.analyze("apartments in Burgas ID 123")
        assert "original_query" in result
        assert "normalized_query" in result
        assert "rrf_weights" in result
        assert "cache_threshold" in result
        assert "is_exact" in result

    def test_analyze_combines_translit_and_weights(self):
        result = _preprocessor.analyze("Sunny Beach корпус 5")
        assert "Солнечный берег" in result["normalized_query"]
        assert result["rrf_weights"]["sparse"] == 0.8
        assert result["is_exact"] is True


class TestQueryPreprocessorHasExactIdentifier:
    """Tests for exact identifier detection."""

    @pytest.mark.parametrize(
        "query",
        [
            pytest.param("квартира ID 12345", id="id_pattern"),
            pytest.param("объект 123456", id="long_number"),
            pytest.param("корпус 5", id="corpus_number"),
            pytest.param("корпус А", id="corpus_letter"),
            pytest.param("блок B", id="block"),
            pytest.param("секция 2", id="section"),
            pytest.param("этаж 5", id="floor"),
            pytest.param("ЖК Елените", id="zhk"),
        ],
    )
    def test_exact_identifier_detected(self, query):
        assert _preprocessor.has_exact_identifier(query) is True

    def test_semantic_query_not_exact(self):
        assert _preprocessor.has_exact_identifier("красивая квартира у моря") is False
