"""Tests for QdrantService with Query API, Score Boosting, and MMR."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestQdrantServiceUnit:
    """Unit tests for QdrantService (no actual Qdrant calls)."""

    def test_init_creates_async_client(self):
        """Test initialization creates AsyncQdrantClient."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_client_class:
            service = QdrantService(
                url="http://localhost:6333",
                api_key="test-key",
                collection_name="test_collection",
            )

            mock_client_class.assert_called_once_with(
                url="http://localhost:6333",
                api_key="test-key",
            )
            assert service._collection_name == "test_collection"

    @pytest.mark.asyncio
    async def test_hybrid_search_rrf_builds_prefetch(self):
        """Test hybrid_search_rrf builds correct prefetch queries."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_client_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            dense_vec = [0.1] * 1024
            sparse_vec = {"indices": [1, 2, 3], "values": [0.5, 0.3, 0.2]}

            await service.hybrid_search_rrf(
                dense_vector=dense_vec,
                sparse_vector=sparse_vec,
                top_k=10,
            )

            # Verify query_points was called
            mock_client.query_points.assert_called_once()
            call_kwargs = mock_client.query_points.call_args[1]

            # Should have prefetch for dense and sparse
            assert "prefetch" in call_kwargs
            assert len(call_kwargs["prefetch"]) == 2

    @pytest.mark.asyncio
    async def test_hybrid_search_rrf_without_sparse(self):
        """Test hybrid_search_rrf works with only dense vector."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_client_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                sparse_vector=None,
                top_k=10,
            )

            call_kwargs = mock_client.query_points.call_args[1]
            # Should have only dense prefetch
            assert len(call_kwargs["prefetch"]) == 1

    @pytest.mark.asyncio
    async def test_search_with_score_boosting(self):
        """Test search_with_score_boosting uses Query API formula."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_client_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            await service.search_with_score_boosting(
                dense_vector=[0.1] * 1024,
                freshness_boost=True,
                freshness_field="created_at",
                freshness_scale_days=7,
                top_k=10,
            )

            mock_client.query_points.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_returns_formatted_results(self):
        """Test search returns properly formatted results."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()

            # Mock point
            mock_point = MagicMock()
            mock_point.id = "test-id"
            mock_point.score = 0.95
            mock_point.payload = {
                "page_content": "Test content",
                "metadata": {"city": "Sofia"},
            }

            mock_client.query_points.return_value = MagicMock(points=[mock_point])
            mock_client_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            results = await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
            )

            assert len(results) == 1
            assert results[0]["id"] == "test-id"
            assert results[0]["score"] == 0.95
            assert results[0]["text"] == "Test content"
            assert results[0]["metadata"]["city"] == "Sofia"


class TestMMRRerank:
    """Tests for MMR diversity reranking."""

    def test_mmr_rerank_selects_diverse_results(self):
        """Test MMR rerank balances relevance and diversity."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("qdrant_client.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            # Create mock points with embeddings
            # Points 0 and 1 are very similar, point 2 is different
            points = [
                {"id": "0", "score": 0.95, "text": "A", "metadata": {}},
                {"id": "1", "score": 0.90, "text": "B", "metadata": {}},
                {"id": "2", "score": 0.85, "text": "C", "metadata": {}},
            ]

            # Embeddings: 0 and 1 are similar, 2 is different
            embeddings = [
                [1.0, 0.0, 0.0],
                [0.99, 0.1, 0.0],  # Very similar to 0
                [0.0, 1.0, 0.0],  # Different
            ]

            result = service.mmr_rerank(
                points=points,
                embeddings=embeddings,
                lambda_mult=0.5,  # Balanced
                top_k=2,
            )

            # Should select point 0 (highest score) first
            assert result[0]["id"] == "0"
            # Second should be point 2 (more diverse) not point 1
            assert result[1]["id"] == "2"

    def test_mmr_rerank_with_high_lambda_prefers_relevance(self):
        """Test MMR with high lambda prefers relevance over diversity."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("qdrant_client.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            points = [
                {"id": "0", "score": 0.95, "text": "A", "metadata": {}},
                {"id": "1", "score": 0.90, "text": "B", "metadata": {}},
                {"id": "2", "score": 0.50, "text": "C", "metadata": {}},
            ]

            embeddings = [
                [1.0, 0.0, 0.0],
                [0.99, 0.1, 0.0],
                [0.0, 1.0, 0.0],
            ]

            result = service.mmr_rerank(
                points=points,
                embeddings=embeddings,
                lambda_mult=1.0,  # Only relevance
                top_k=2,
            )

            # Should select by score only: 0, then 1
            assert result[0]["id"] == "0"
            assert result[1]["id"] == "1"

    def test_mmr_rerank_returns_all_if_fewer_than_top_k(self):
        """Test MMR returns all points if fewer than top_k."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("qdrant_client.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            points = [
                {"id": "0", "score": 0.95, "text": "A", "metadata": {}},
            ]
            embeddings = [[1.0, 0.0]]

            result = service.mmr_rerank(
                points=points,
                embeddings=embeddings,
                top_k=10,
            )

            assert len(result) == 1


class TestFilterBuilding:
    """Tests for Qdrant filter building."""

    def test_build_filter_with_exact_match(self):
        """Test filter building with exact match values."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("qdrant_client.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            qdrant_filter = service._build_filter({"city": "Sofia", "rooms": 2})

            assert qdrant_filter is not None
            assert len(qdrant_filter.must) == 2

    def test_build_filter_with_range(self):
        """Test filter building with range values."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("qdrant_client.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            qdrant_filter = service._build_filter({"price": {"gte": 50000, "lte": 100000}})

            assert qdrant_filter is not None
            assert len(qdrant_filter.must) == 1

    def test_build_filter_returns_none_for_empty(self):
        """Test filter building returns None for empty filters."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("qdrant_client.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            assert service._build_filter({}) is None
            assert service._build_filter(None) is None
