"""Tests for HybridRetrieverService."""

import pytest
from unittest.mock import MagicMock, patch


class TestHybridRetrieverServiceUnit:
    """Unit tests for HybridRetrieverService."""

    def test_hybrid_search_uses_prefetch(self):
        """Test hybrid search uses prefetch with dense and sparse."""
        from telegram_bot.services.hybrid_retriever import HybridRetrieverService

        with patch('telegram_bot.services.hybrid_retriever.QdrantClient') as mock_client_class:
            mock_client = MagicMock()
            mock_point = MagicMock()
            mock_point.payload = {"page_content": "test", "metadata": {}}
            mock_point.score = 0.9
            mock_client.query_points.return_value = MagicMock(points=[mock_point])
            mock_client.get_collections.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            service = HybridRetrieverService(
                url="http://localhost:6333",
                api_key="",
                collection_name="test"
            )

            results = service.hybrid_search(
                dense_vector=[0.1] * 1024,
                sparse_indices=[1, 2, 3],
                sparse_values=[0.5, 0.3, 0.2],
                rrf_weights=(0.6, 0.4),
            )

            assert len(results) == 1
            # Verify prefetch was used
            call_kwargs = mock_client.query_points.call_args[1]
            assert "prefetch" in call_kwargs

    def test_applies_dynamic_rrf_weights(self):
        """Test RRF weights affect prefetch limits."""
        from telegram_bot.services.hybrid_retriever import HybridRetrieverService

        with patch('telegram_bot.services.hybrid_retriever.QdrantClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_client.get_collections.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            service = HybridRetrieverService(
                url="http://localhost:6333",
                api_key="",
                collection_name="test"
            )

            # Sparse-favored weights (0.2, 0.8)
            service.hybrid_search(
                dense_vector=[0.1] * 1024,
                sparse_indices=[1],
                sparse_values=[0.5],
                rrf_weights=(0.2, 0.8),
                top_k=10,
            )

            call_kwargs = mock_client.query_points.call_args[1]
            prefetch = call_kwargs["prefetch"]
            # With sparse-favored, sparse prefetch should have higher limit
            dense_prefetch = [p for p in prefetch if "dense" in str(p.using)][0]
            sparse_prefetch = [p for p in prefetch if "sparse" in str(p.using)][0]
            assert sparse_prefetch.limit >= dense_prefetch.limit

    def test_builds_filter_correctly(self):
        """Test filter building includes base filter."""
        from telegram_bot.services.hybrid_retriever import HybridRetrieverService

        with patch('telegram_bot.services.hybrid_retriever.QdrantClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_client.get_collections.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            service = HybridRetrieverService(
                url="http://localhost:6333",
                api_key="",
                collection_name="test"
            )

            service.hybrid_search(
                dense_vector=[0.1] * 1024,
                sparse_indices=[1],
                sparse_values=[0.5],
                filters={"city": "Бургас"},
            )

            call_kwargs = mock_client.query_points.call_args[1]
            assert "query_filter" in call_kwargs

    def test_graceful_degradation_on_error(self):
        """Test returns empty list on error."""
        from telegram_bot.services.hybrid_retriever import HybridRetrieverService

        with patch('telegram_bot.services.hybrid_retriever.QdrantClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.query_points.side_effect = Exception("Connection error")
            mock_client.get_collections.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            service = HybridRetrieverService(
                url="http://localhost:6333",
                api_key="",
                collection_name="test"
            )

            results = service.hybrid_search(
                dense_vector=[0.1] * 1024,
                sparse_indices=[1],
                sparse_values=[0.5],
            )

            assert results == []

    def test_fallback_to_dense_only(self):
        """Test fallback to dense-only search when no sparse vectors."""
        from telegram_bot.services.hybrid_retriever import HybridRetrieverService

        with patch('telegram_bot.services.hybrid_retriever.QdrantClient') as mock_client_class:
            mock_client = MagicMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_client.get_collections.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            service = HybridRetrieverService(
                url="http://localhost:6333",
                api_key="",
                collection_name="test"
            )

            # No sparse vectors provided
            service.hybrid_search(
                dense_vector=[0.1] * 1024,
                sparse_indices=[],
                sparse_values=[],
            )

            # Should still work (dense-only fallback)
            assert mock_client.query_points.called
