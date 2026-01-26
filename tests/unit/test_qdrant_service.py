"""Tests for QdrantService quantization parameters."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.qdrant import QdrantService


class TestQdrantServiceQuantization:
    """Test quantization search parameters."""

    @pytest.fixture
    def service(self):
        """Create QdrantService with mocked client."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
            )
            service._client = AsyncMock()
            return service

    @pytest.mark.asyncio
    async def test_hybrid_search_with_quantization_ignore(self, service):
        """Test that quantization_ignore is passed to search params."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            quantization_ignore=True,
        )

        call_kwargs = service._client.query_points.call_args.kwargs
        assert "search_params" in call_kwargs
        assert call_kwargs["search_params"] is not None

    @pytest.mark.asyncio
    async def test_hybrid_search_default_no_quantization_params(self, service):
        """Test default behavior without quantization params."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.hybrid_search_rrf(dense_vector=[0.1] * 1024)

        call_kwargs = service._client.query_points.call_args.kwargs
        assert call_kwargs.get("search_params") is None

    @pytest.mark.asyncio
    async def test_quantization_params_values(self, service):
        """Test that ignore/rescore/oversampling values are correctly set."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        # Test with specific values
        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            quantization_ignore=True,
            quantization_rescore=False,
            quantization_oversampling=3.0,
        )

        call_kwargs = service._client.query_points.call_args.kwargs
        search_params = call_kwargs["search_params"]

        # Verify all quantization params are correctly passed
        assert search_params is not None
        assert search_params.quantization.ignore is True
        assert search_params.quantization.rescore is False
        assert search_params.quantization.oversampling == 3.0

    @pytest.mark.asyncio
    async def test_quantization_default_rescore_oversampling(self, service):
        """Test default rescore=True and oversampling=2.0."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        # Only set ignore, check defaults for rescore/oversampling
        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            quantization_ignore=False,
        )

        call_kwargs = service._client.query_points.call_args.kwargs
        search_params = call_kwargs["search_params"]

        assert search_params.quantization.ignore is False
        assert search_params.quantization.rescore is True  # default
        assert search_params.quantization.oversampling == 2.0  # default


class TestQdrantServiceMMR:
    """Tests for MMR (Maximal Marginal Relevance) reranking."""

    @pytest.fixture
    def service(self):
        """Create QdrantService with mocked client."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            return QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
            )

    def test_mmr_rerank_basic(self, service):
        """Test basic MMR reranking returns correct number of results."""
        points = [
            {"id": "1", "text": "doc1", "score": 0.9},
            {"id": "2", "text": "doc2", "score": 0.8},
            {"id": "3", "text": "doc3", "score": 0.7},
            {"id": "4", "text": "doc4", "score": 0.6},
            {"id": "5", "text": "doc5", "score": 0.5},
        ]
        embeddings = [
            [1.0, 0.0, 0.0],
            [0.9, 0.1, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.9, 0.1],
            [0.0, 0.0, 1.0],
        ]

        result = service.mmr_rerank(points=points, embeddings=embeddings, top_k=3)

        assert len(result) == 3
        # First should be highest score
        assert result[0]["id"] == "1"

    def test_mmr_rerank_diversity(self, service):
        """Test MMR promotes diversity over pure relevance."""
        points = [
            {"id": "1", "text": "doc1", "score": 0.9},
            {"id": "2", "text": "doc2", "score": 0.85},  # High score but similar to 1
            {"id": "3", "text": "doc3", "score": 0.7},  # Lower score but very different
        ]
        # Doc 2 is very similar to doc 1, doc 3 is orthogonal
        embeddings = [
            [1.0, 0.0],  # doc1
            [0.99, 0.01],  # doc2 - nearly identical to doc1
            [0.0, 1.0],  # doc3 - completely different
        ]

        result = service.mmr_rerank(points=points, embeddings=embeddings, lambda_mult=0.5, top_k=2)

        # First should be highest score (doc1)
        assert result[0]["id"] == "1"
        # Second should prefer diversity - doc3 over doc2 despite lower score
        assert result[1]["id"] == "3"

    def test_mmr_rerank_lambda_1_relevance_only(self, service):
        """Test lambda=1.0 results in pure relevance ranking."""
        points = [
            {"id": "1", "text": "doc1", "score": 0.9},
            {"id": "2", "text": "doc2", "score": 0.8},
            {"id": "3", "text": "doc3", "score": 0.7},
        ]
        embeddings = [
            [1.0, 0.0],
            [0.99, 0.01],  # Very similar to doc1
            [0.0, 1.0],  # Very different
        ]

        result = service.mmr_rerank(points=points, embeddings=embeddings, lambda_mult=1.0, top_k=3)

        # With lambda=1.0, should be pure relevance order
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "2"
        assert result[2]["id"] == "3"

    def test_mmr_rerank_lambda_0_diversity_only(self, service):
        """Test lambda=0.0 results in maximum diversity."""
        points = [
            {"id": "1", "text": "doc1", "score": 0.9},
            {"id": "2", "text": "doc2", "score": 0.85},
            {"id": "3", "text": "doc3", "score": 0.7},
        ]
        embeddings = [
            [1.0, 0.0],  # doc1
            [0.99, 0.01],  # doc2 - similar to doc1
            [0.0, 1.0],  # doc3 - different
        ]

        result = service.mmr_rerank(points=points, embeddings=embeddings, lambda_mult=0.0, top_k=2)

        # First is still highest score
        assert result[0]["id"] == "1"
        # With lambda=0, should strongly prefer diversity
        assert result[1]["id"] == "3"

    def test_mmr_rerank_empty_input(self, service):
        """Test MMR with empty input returns empty."""
        result = service.mmr_rerank(points=[], embeddings=[], top_k=5)

        assert result == []

    def test_mmr_rerank_fewer_points_than_top_k(self, service):
        """Test MMR returns all points when fewer than top_k."""
        points = [
            {"id": "1", "text": "doc1", "score": 0.9},
            {"id": "2", "text": "doc2", "score": 0.8},
        ]
        embeddings = [[1.0, 0.0], [0.0, 1.0]]

        result = service.mmr_rerank(points=points, embeddings=embeddings, top_k=10)

        # Should return all points unchanged
        assert len(result) == 2
        assert result == points

    def test_mmr_rerank_equal_points_and_top_k(self, service):
        """Test MMR with exactly top_k points returns all unchanged."""
        points = [
            {"id": "1", "text": "doc1", "score": 0.9},
            {"id": "2", "text": "doc2", "score": 0.8},
            {"id": "3", "text": "doc3", "score": 0.7},
        ]
        embeddings = [[1.0, 0.0], [0.5, 0.5], [0.0, 1.0]]

        result = service.mmr_rerank(points=points, embeddings=embeddings, top_k=3)

        assert len(result) == 3

    def test_mmr_rerank_single_point(self, service):
        """Test MMR with single point returns that point."""
        points = [{"id": "1", "text": "doc1", "score": 0.9}]
        embeddings = [[1.0, 0.0]]

        result = service.mmr_rerank(points=points, embeddings=embeddings, top_k=5)

        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_mmr_rerank_preserves_point_structure(self, service):
        """Test MMR preserves full point structure."""
        points = [
            {"id": "1", "text": "doc1", "score": 0.9, "metadata": {"source": "a"}},
            {"id": "2", "text": "doc2", "score": 0.8, "metadata": {"source": "b"}},
            {"id": "3", "text": "doc3", "score": 0.7, "metadata": {"source": "c"}},
            {"id": "4", "text": "doc4", "score": 0.6, "metadata": {"source": "d"}},
        ]
        embeddings = [[1.0, 0.0], [0.5, 0.5], [0.0, 1.0], [0.3, 0.7]]

        result = service.mmr_rerank(points=points, embeddings=embeddings, top_k=2)

        # Should preserve all fields
        for point in result:
            assert "id" in point
            assert "text" in point
            assert "score" in point
            assert "metadata" in point
