"""Integration tests for query preprocessing pipeline.

Tests QueryPreprocessor transliteration, query type detection, and cache thresholds.
Legacy Voyage-specific tests removed — VoyageEmbeddingService/VoyageRerankerService/VoyageClient
were replaced by unified VoyageService.
"""

from telegram_bot.services import QueryPreprocessor


class TestQueryPreprocessorPipeline:
    """Integration tests for QueryPreprocessor in search pipeline context."""

    def test_translit_improves_sparse_search(self):
        """Test that transliteration improves search for Latin place names."""
        preprocessor = QueryPreprocessor()

        # Latin input
        result = preprocessor.analyze("villa in Sveti Vlas near beach")

        # Should be normalized to Cyrillic
        assert "Святой Влас" in result["normalized_query"]
        assert "Sveti Vlas" not in result["normalized_query"]

        # Should still be semantic query (no IDs/corpus)
        assert result["rrf_weights"]["dense"] == 0.6
        assert result["is_exact"] is False

    def test_exact_query_detection(self):
        """Test exact query patterns are detected correctly."""
        preprocessor = QueryPreprocessor()

        exact_queries = [
            "квартира ID 12345",
            "ЖК Елените корпус 5",
            "апартаменты этаж 3",
            "блок А цена",
        ]

        for query in exact_queries:
            result = preprocessor.analyze(query)
            assert result["is_exact"] is True, f"Failed for: {query}"
            assert result["rrf_weights"]["sparse"] == 0.8, f"Failed for: {query}"
            assert result["cache_threshold"] == 0.05, f"Failed for: {query}"

    def test_semantic_query_detection(self):
        """Test semantic queries use dense-favored weights."""
        preprocessor = QueryPreprocessor()

        semantic_queries = [
            "квартиры у моря с видом",
            "недорогое жилье в центре",
            "апартаменты для семьи с детьми",
        ]

        for query in semantic_queries:
            result = preprocessor.analyze(query)
            assert result["is_exact"] is False, f"Failed for: {query}"
            assert result["rrf_weights"]["dense"] == 0.6, f"Failed for: {query}"
            assert result["cache_threshold"] == 0.10, f"Failed for: {query}"

    def test_cache_threshold_adaptive(self):
        """Test cache threshold adapts to query type."""
        preprocessor = QueryPreprocessor()

        # General query - default threshold
        result = preprocessor.analyze("квартиры в центре города")
        assert result["cache_threshold"] == 0.10

        # Query with number - strict threshold
        result = preprocessor.analyze("квартира номер 12345")
        assert result["cache_threshold"] == 0.05

        # Query with corpus - strict threshold
        result = preprocessor.analyze("корпус Б апартаменты")
        assert result["cache_threshold"] == 0.05


class TestQueryPreprocessorEdgeCases:
    """Edge case tests for QueryPreprocessor."""

    def test_multiple_translit_replacements(self):
        """Test query with multiple Latin place names."""
        preprocessor = QueryPreprocessor()

        result = preprocessor.analyze("apartments between Sunny Beach and Sveti Vlas")

        assert "Солнечный берег" in result["normalized_query"]
        assert "Святой Влас" in result["normalized_query"]
        assert "Sunny Beach" not in result["normalized_query"]
        assert "Sveti Vlas" not in result["normalized_query"]

    def test_case_insensitive_translit(self):
        """Test transliteration works regardless of case."""
        preprocessor = QueryPreprocessor()

        # Lowercase
        result1 = preprocessor.analyze("villa in sunny beach")
        assert "Солнечный берег" in result1["normalized_query"]

        # Uppercase
        result2 = preprocessor.analyze("villa in SUNNY BEACH")
        assert "Солнечный берег" in result2["normalized_query"]

        # Mixed case
        result3 = preprocessor.analyze("villa in SuNnY BeAcH")
        assert "Солнечный берег" in result3["normalized_query"]

    def test_empty_query(self):
        """Test handling of empty query."""
        preprocessor = QueryPreprocessor()

        result = preprocessor.analyze("")

        assert result["normalized_query"] == ""
        assert result["is_exact"] is False
        assert result["rrf_weights"]["dense"] == 0.6

    def test_cyrillic_passthrough(self):
        """Test Cyrillic queries pass through unchanged."""
        preprocessor = QueryPreprocessor()

        original = "квартиры в Солнечном берегу"
        result = preprocessor.analyze(original)

        assert result["normalized_query"] == original
