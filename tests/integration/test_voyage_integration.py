"""Integration tests for Voyage Unified RAG pipeline."""

from unittest.mock import MagicMock, patch

import pytest


class TestVoyagePipelineIntegration:
    """Integration tests for complete Voyage pipeline."""

    def test_full_search_pipeline_sync(self):
        """Test complete search pipeline: preprocess -> embed -> retrieve -> rerank."""
        from telegram_bot.services.voyage_client import VoyageClient

        from telegram_bot.services import (
            QueryPreprocessor,
            VoyageEmbeddingService,
            VoyageRerankerService,
        )

        # Reset singleton before test
        VoyageClient._instance = None

        # Setup mocks
        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client") as mock_voyage_client,
        ):
            # Mock embed method
            mock_client_instance = MagicMock()
            mock_embed_result = MagicMock()
            mock_embed_result.embeddings = [[0.1] * 1024]
            mock_client_instance.embed.return_value = mock_embed_result

            # Mock rerank method
            mock_rerank_result = MagicMock()
            mock_rerank_item_1 = MagicMock()
            mock_rerank_item_1.index = 1
            mock_rerank_item_1.relevance_score = 0.95
            mock_rerank_item_2 = MagicMock()
            mock_rerank_item_2.index = 0
            mock_rerank_item_2.relevance_score = 0.80
            mock_rerank_result.results = [mock_rerank_item_1, mock_rerank_item_2]
            mock_client_instance.rerank.return_value = mock_rerank_result

            mock_voyage_client.return_value = mock_client_instance

            # 1. Preprocess query
            preprocessor = QueryPreprocessor()
            analysis = preprocessor.analyze("apartments in Sunny Beach корпус 5")

            assert "Солнечный берег" in analysis["normalized_query"]
            assert analysis["rrf_weights"]["sparse"] == 0.8  # Exact query
            assert analysis["is_exact"] is True

            # 2. Embed query
            embedding_service = VoyageEmbeddingService()
            query_vector = embedding_service.embed_query_sync(analysis["normalized_query"])

            assert len(query_vector) == 1024

            # 3. Simulate retrieval results
            retrieval_results = [
                {
                    "text": "Апартаменты в Солнечном берегу, корпус 3",
                    "metadata": {"id": 1},
                    "score": 0.85,
                },
                {
                    "text": "Апартаменты в Солнечном берегу, корпус 5",
                    "metadata": {"id": 2},
                    "score": 0.82,
                },
            ]

            # 4. Rerank results
            reranker = VoyageRerankerService()
            reranked = reranker.rerank_sync(
                analysis["normalized_query"], retrieval_results, top_k=2
            )

            # Verify reranking worked
            assert len(reranked) == 2
            assert reranked[0]["rerank_score"] == 0.95
            assert "original_score" in reranked[0]

        # Cleanup
        VoyageClient._instance = None

    def test_translit_improves_sparse_search(self):
        """Test that transliteration improves search for Latin place names."""
        from telegram_bot.services import QueryPreprocessor

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
        from telegram_bot.services import QueryPreprocessor

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
        from telegram_bot.services import QueryPreprocessor

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
    async def test_async_pipeline(self):
        """Test async methods work correctly."""
        from telegram_bot.services.voyage_client import VoyageClient

        from telegram_bot.services import VoyageEmbeddingService, VoyageRerankerService

        # Reset singleton
        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client") as mock_voyage_client,
        ):
            # Mock embed method
            mock_client_instance = MagicMock()
            mock_embed_result = MagicMock()
            mock_embed_result.embeddings = [[0.1] * 1024]
            mock_client_instance.embed.return_value = mock_embed_result

            # Mock rerank method
            mock_rerank_result = MagicMock()
            mock_rerank_item = MagicMock()
            mock_rerank_item.index = 0
            mock_rerank_item.relevance_score = 0.9
            mock_rerank_result.results = [mock_rerank_item]
            mock_client_instance.rerank.return_value = mock_rerank_result

            mock_voyage_client.return_value = mock_client_instance

            # Test async embedding
            embed_service = VoyageEmbeddingService()
            vector = await embed_service.embed_query("test query")
            assert len(vector) == 1024

            # Test async reranking
            rerank_service = VoyageRerankerService()
            docs = [{"text": "doc", "metadata": {}}]
            reranked = await rerank_service.rerank("query", docs)
            assert len(reranked) == 1

        # Cleanup
        VoyageClient._instance = None

    def test_cache_threshold_adaptive(self):
        """Test cache threshold adapts to query type."""
        from telegram_bot.services import QueryPreprocessor

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


class TestVoyageClientSingleton:
    """Test VoyageClient singleton behavior."""

    def test_singleton_shared_across_services(self):
        """Test all services share same VoyageClient instance."""
        from telegram_bot.services.voyage_client import VoyageClient

        # Reset singleton
        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client"),
        ):
            # Get instances from different entry points
            client1 = VoyageClient.get_instance()
            client2 = VoyageClient.get_instance()

            assert client1 is client2

        # Cleanup
        VoyageClient._instance = None

    def test_singleton_reset(self):
        """Test singleton reset functionality."""
        from telegram_bot.services.voyage_client import VoyageClient

        # Reset singleton
        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client"),
        ):
            client1 = VoyageClient.get_instance()
            VoyageClient.reset_instance()
            client2 = VoyageClient.get_instance()

            assert client1 is not client2

        # Cleanup
        VoyageClient._instance = None


class TestQueryPreprocessorEdgeCases:
    """Edge case tests for QueryPreprocessor."""

    def test_multiple_translit_replacements(self):
        """Test query with multiple Latin place names."""
        from telegram_bot.services import QueryPreprocessor

        preprocessor = QueryPreprocessor()

        result = preprocessor.analyze("apartments between Sunny Beach and Sveti Vlas")

        assert "Солнечный берег" in result["normalized_query"]
        assert "Святой Влас" in result["normalized_query"]
        assert "Sunny Beach" not in result["normalized_query"]
        assert "Sveti Vlas" not in result["normalized_query"]

    def test_case_insensitive_translit(self):
        """Test transliteration works regardless of case."""
        from telegram_bot.services import QueryPreprocessor

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
        from telegram_bot.services import QueryPreprocessor

        preprocessor = QueryPreprocessor()

        result = preprocessor.analyze("")

        assert result["normalized_query"] == ""
        assert result["is_exact"] is False
        assert result["rrf_weights"]["dense"] == 0.6

    def test_cyrillic_passthrough(self):
        """Test Cyrillic queries pass through unchanged."""
        from telegram_bot.services import QueryPreprocessor

        preprocessor = QueryPreprocessor()

        original = "квартиры в Солнечном берегу"
        result = preprocessor.analyze(original)

        assert result["normalized_query"] == original


class TestVoyageEmbeddingServiceBatching:
    """Test VoyageEmbeddingService batch processing."""

    def test_document_batching(self):
        """Test documents are batched correctly for embedding."""
        from telegram_bot.services.voyage_client import VoyageClient

        from telegram_bot.services import VoyageEmbeddingService

        # Reset singleton
        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client") as mock_voyage_client,
        ):
            mock_client_instance = MagicMock()

            # Return embeddings matching the batch size dynamically
            def mock_embed(texts, model, input_type):
                result = MagicMock()
                result.embeddings = [[0.1] * 1024] * len(texts)
                return result

            mock_client_instance.embed.side_effect = mock_embed

            mock_voyage_client.return_value = mock_client_instance

            service = VoyageEmbeddingService()

            # Create 150 documents (should trigger 2 batches: 128 + 22)
            docs = [f"document {i}" for i in range(150)]
            embeddings = service.embed_documents_sync(docs)

            # Verify embed was called twice (batched)
            assert mock_client_instance.embed.call_count == 2
            assert len(embeddings) == 150

        # Cleanup
        VoyageClient._instance = None

    def test_empty_documents_list(self):
        """Test handling of empty documents list."""
        from telegram_bot.services.voyage_client import VoyageClient

        from telegram_bot.services import VoyageEmbeddingService

        # Reset singleton
        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client") as mock_voyage_client,
        ):
            mock_client_instance = MagicMock()
            mock_voyage_client.return_value = mock_client_instance

            service = VoyageEmbeddingService()

            # Empty list should return empty list without API call
            embeddings = service.embed_documents_sync([])

            assert embeddings == []
            mock_client_instance.embed.assert_not_called()

        # Cleanup
        VoyageClient._instance = None


class TestVoyageRerankerEdgeCases:
    """Edge case tests for VoyageRerankerService."""

    def test_empty_documents_rerank(self):
        """Test reranking with empty documents list."""
        from telegram_bot.services.voyage_client import VoyageClient

        from telegram_bot.services import VoyageRerankerService

        # Reset singleton
        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client") as mock_voyage_client,
        ):
            mock_client_instance = MagicMock()
            mock_voyage_client.return_value = mock_client_instance

            service = VoyageRerankerService()

            # Empty list should return empty list without API call
            reranked = service.rerank_sync("query", [])

            assert reranked == []
            mock_client_instance.rerank.assert_not_called()

        # Cleanup
        VoyageClient._instance = None

    def test_page_content_fallback(self):
        """Test reranker uses page_content if text is missing."""
        from telegram_bot.services.voyage_client import VoyageClient

        from telegram_bot.services import VoyageRerankerService

        # Reset singleton
        VoyageClient._instance = None

        with (
            patch.dict("os.environ", {"VOYAGE_API_KEY": "test-key"}),
            patch("voyageai.Client") as mock_voyage_client,
        ):
            mock_client_instance = MagicMock()

            mock_rerank_result = MagicMock()
            mock_rerank_item = MagicMock()
            mock_rerank_item.index = 0
            mock_rerank_item.relevance_score = 0.85
            mock_rerank_result.results = [mock_rerank_item]
            mock_client_instance.rerank.return_value = mock_rerank_result

            mock_voyage_client.return_value = mock_client_instance

            service = VoyageRerankerService()

            # Document with page_content instead of text
            docs = [{"page_content": "content from langchain", "metadata": {"id": 1}}]
            reranked = service.rerank_sync("query", docs)

            assert len(reranked) == 1
            assert reranked[0]["text"] == "content from langchain"

        # Cleanup
        VoyageClient._instance = None
