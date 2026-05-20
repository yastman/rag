"""Tests for QueryPreprocessor."""

import re
from unittest.mock import patch

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


class TestQueryPreprocessorTranslitPrecompiled:
    """Tests for precompiled transliteration patterns (issue #1644).

    The static TRANSLIT_MAP allows pattern compilation to be hoisted out of the
    per-query hot path. These tests pin the contract:

    1. ``normalize_translit`` MUST NOT call ``re.compile`` after the class /
       module has been imported (compilation is a one-time cost).
    2. Output for every supported Latin -> Cyrillic mapping MUST stay
       byte-identical to the legacy per-call ``re.compile`` implementation.
    3. The IGNORECASE flag MUST be preserved (e.g. ``"BURGAS"`` -> ``"Бургас"``).
    """

    def test_translit_patterns_compiled_once(self):
        """``re.compile`` must NOT be invoked inside the per-query hot path.

        Patterns derived from the static ``TRANSLIT_MAP`` should be compiled
        once (at class definition / module import) and reused thereafter. We
        patch ``re.compile`` AFTER import, then call ``normalize_translit``
        many times and assert no compilations were triggered.
        """
        pp = QueryPreprocessor()
        # Warm up to defeat any lazy first-call init; subsequent calls must hit
        # zero compilations regardless.
        pp.normalize_translit("warmup Burgas")

        queries = [
            "Burgas",
            "Sunny Beach",
            "Sveti Vlas Albena Nesebar",
            "BURGAS apartment in Varna",
            "квартира в Sofia рядом с Albena",
            "Golden Sands hotel in Sozopol",
        ]

        with patch("re.compile", wraps=re.compile) as mock_compile:
            for q in queries:
                pp.normalize_translit(q)
            assert mock_compile.call_count == 0, (
                "normalize_translit should not call re.compile in the hot path; "
                f"got {mock_compile.call_count} compilations across "
                f"{len(queries)} queries. Precompile patterns at class/module "
                "load time."
            )

    @pytest.mark.parametrize(
        ("latin_input", "expected_output"),
        [
            # Cities (single-token)
            pytest.param("apartments in Burgas", "apartments in Бургас", id="burgas"),
            pytest.param("flights to Varna", "flights to Варна", id="varna"),
            pytest.param("hotel in Sofia", "hotel in София", id="sofia"),
            # Resorts (multi-word phrase — must match as a phrase)
            pytest.param(
                "Sunny Beach apartments",
                "Солнечный берег apartments",
                id="sunny_beach_phrase",
            ),
            pytest.param(
                "villa in Sveti Vlas",
                "villa in Святой Влас",
                id="sveti_vlas_phrase",
            ),
            # Variant spellings collapse to the same Cyrillic form
            pytest.param("Nessebar old town", "Несебър old town", id="nessebar_variant"),
            pytest.param("Golden Sands hotel", "Золотые пески hotel", id="golden_sands"),
        ],
    )
    def test_translit_output_unchanged(self, latin_input, expected_output):
        """Byte-identical output guarantee vs. the legacy implementation.

        These exact strings were captured from the per-call ``re.compile``
        version — any deviation here is a behaviour regression.
        """
        assert _preprocessor.normalize_translit(latin_input) == expected_output

    @pytest.mark.parametrize(
        ("query", "expected"),
        [
            pytest.param("BURGAS", "Бургас", id="all_upper"),
            pytest.param("burgas", "Бургас", id="all_lower"),
            pytest.param("BuRgAs", "Бургас", id="mixed_case"),
            pytest.param("SUNNY BEACH", "Солнечный берег", id="upper_phrase"),
            pytest.param("sunny beach", "Солнечный берег", id="lower_phrase"),
        ],
    )
    def test_translit_handles_case_insensitivity(self, query, expected):
        """The IGNORECASE flag must be preserved across the refactor."""
        assert _preprocessor.normalize_translit(query) == expected


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
