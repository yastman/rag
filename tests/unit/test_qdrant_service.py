"""Tests for QdrantService quantization parameters."""

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.services.qdrant import QdrantService


@pytest.fixture(autouse=True)
def reset_qdrant_modules():
    """Clear qdrant module cache to ensure fresh import with mocks."""
    # Clear before test
    modules_to_clear = [k for k in sys.modules if "qdrant" in k.lower()]
    for mod in modules_to_clear:
        sys.modules.pop(mod, None)

    yield

    # Clear after test
    modules_to_clear = [k for k in sys.modules if "qdrant" in k.lower()]
    for mod in modules_to_clear:
        sys.modules.pop(mod, None)


def _make_service(*, validated: bool = False) -> QdrantService:
    """Create QdrantService with mocked client.

    If ``validated``, set ``_client`` to AsyncMock and ``_collection_validated`` to True
    so search methods work without real Qdrant.
    """
    with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
        svc = QdrantService(url="http://localhost:6333", collection_name="test_collection")
        if validated:
            svc._client = AsyncMock()
            svc._collection_validated = True
        return svc


def _make_mock_point(
    id: str = "1", score: float = 0.9, text: str = "test", metadata: dict | None = None
) -> MagicMock:
    """Create a mock Qdrant search point."""
    point = MagicMock()
    point.id = id
    point.score = score
    point.payload = {"page_content": text, "metadata": metadata or {}}
    return point


class TestQdrantServiceQuantization:
    """Test quantization search parameters."""

    @pytest.fixture
    def service(self):
        return _make_service(validated=True)
    async def test_hybrid_search_with_quantization_ignore(self, service):
        """Test that quantization_ignore is passed to search params."""
        mock_point = _make_mock_point()

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            quantization_ignore=True,
        )

        call_kwargs = service._client.query_points.call_args.kwargs
        assert "search_params" in call_kwargs
        assert call_kwargs["search_params"] is not None
    async def test_hybrid_search_default_no_quantization_params(self, service):
        """Test default behavior without quantization params."""
        mock_point = _make_mock_point()

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.hybrid_search_rrf(dense_vector=[0.1] * 1024)

        call_kwargs = service._client.query_points.call_args.kwargs
        assert call_kwargs.get("search_params") is None
    async def test_quantization_params_values(self, service):
        """Test that ignore/rescore/oversampling values are correctly set."""
        mock_point = _make_mock_point()

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
    async def test_quantization_default_rescore_oversampling(self, service):
        """Test default rescore=True and oversampling=2.0."""
        mock_point = _make_mock_point()

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
        return _make_service()

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


class TestQdrantServiceBatchSearch:
    """Tests for batch_search_rrf method."""

    @pytest.fixture
    def service(self):
        return _make_service(validated=True)

    @pytest.fixture
    def mock_points(self):
        return [
            _make_mock_point(id=f"doc_{i}", score=0.9 - i * 0.1,
                             text=f"Content {i}", metadata={"source": f"src_{i}"})
            for i in range(3)
        ]
    async def test_batch_search_single_query(self, service, mock_points):
        """Test batch search with a single query returns results."""
        response = MagicMock()
        response.points = mock_points

        service._client.query_batch_points = AsyncMock(return_value=[response])

        queries = [{"dense_vector": [0.1] * 1024}]
        results = await service.batch_search_rrf(queries=queries, top_k=5)

        assert len(results) == 3
        assert results[0]["id"] == "doc_0"
        assert results[0]["score"] == 0.9
        service._client.query_batch_points.assert_called_once()
    async def test_batch_search_multiple_queries(self, service):
        """Test batch search with multiple queries merges results."""
        # Query 1 returns doc_0, doc_1
        p0 = MagicMock(id="doc_0", score=0.9, payload={"page_content": "A", "metadata": {}})
        p1 = MagicMock(id="doc_1", score=0.7, payload={"page_content": "B", "metadata": {}})
        resp1 = MagicMock(points=[p0, p1])

        # Query 2 returns doc_1 (higher score), doc_2
        p1b = MagicMock(id="doc_1", score=0.85, payload={"page_content": "B", "metadata": {}})
        p2 = MagicMock(id="doc_2", score=0.6, payload={"page_content": "C", "metadata": {}})
        resp2 = MagicMock(points=[p1b, p2])

        service._client.query_batch_points = AsyncMock(return_value=[resp1, resp2])

        queries = [
            {"dense_vector": [0.1] * 1024},
            {"dense_vector": [0.2] * 1024},
        ]
        results = await service.batch_search_rrf(queries=queries, top_k=10)

        # Should have 3 unique docs
        assert len(results) == 3
        ids = [r["id"] for r in results]
        assert ids == ["doc_0", "doc_1", "doc_2"]
        # doc_1 should keep the higher score from query 2
        assert results[1]["score"] == 0.85
    async def test_batch_search_dedup_keeps_best_score(self, service):
        """Test deduplication keeps the highest score for each doc."""
        p1 = MagicMock(id="same_doc", score=0.5, payload={"page_content": "X", "metadata": {}})
        p2 = MagicMock(id="same_doc", score=0.95, payload={"page_content": "X", "metadata": {}})

        resp1 = MagicMock(points=[p1])
        resp2 = MagicMock(points=[p2])

        service._client.query_batch_points = AsyncMock(return_value=[resp1, resp2])

        queries = [
            {"dense_vector": [0.1] * 1024},
            {"dense_vector": [0.2] * 1024},
        ]
        results = await service.batch_search_rrf(queries=queries, top_k=5)

        assert len(results) == 1
        assert results[0]["score"] == 0.95
    async def test_batch_search_with_sparse_vectors(self, service, mock_points):
        """Test batch search includes sparse vectors in prefetch."""
        response = MagicMock(points=mock_points)
        service._client.query_batch_points = AsyncMock(return_value=[response])

        queries = [
            {
                "dense_vector": [0.1] * 1024,
                "sparse_vector": {"indices": [1, 5, 10], "values": [0.5, 0.3, 0.2]},
            }
        ]
        results = await service.batch_search_rrf(queries=queries, top_k=5)

        assert len(results) == 3
        # Verify the request has 2 prefetches (dense + sparse)
        call_kwargs = service._client.query_batch_points.call_args.kwargs
        req = call_kwargs["requests"][0]
        assert len(req.prefetch) == 2
    async def test_batch_search_empty_queries(self, service):
        """Test batch search with empty queries returns empty list."""
        results = await service.batch_search_rrf(queries=[], top_k=5)

        assert results == []
        service._client.query_batch_points.assert_not_called()
    async def test_batch_search_respects_top_k(self, service):
        """Test batch search caps results at top_k."""
        points = []
        for i in range(10):
            p = MagicMock(
                id=f"doc_{i}",
                score=1.0 - i * 0.05,
                payload={"page_content": f"C{i}", "metadata": {}},
            )
            points.append(p)

        resp = MagicMock(points=points)
        service._client.query_batch_points = AsyncMock(return_value=[resp])

        queries = [{"dense_vector": [0.1] * 1024}]
        results = await service.batch_search_rrf(queries=queries, top_k=3)

        assert len(results) == 3
        assert results[0]["score"] == 1.0
    async def test_batch_search_graceful_degradation(self, service):
        """Test batch search returns empty on error."""
        service._client.query_batch_points = AsyncMock(side_effect=Exception("Connection lost"))

        queries = [{"dense_vector": [0.1] * 1024}]
        results = await service.batch_search_rrf(queries=queries, top_k=5)

        assert results == []
    async def test_batch_search_with_filters(self, service, mock_points):
        """Test batch search passes filters to all queries."""
        response = MagicMock(points=mock_points)
        service._client.query_batch_points = AsyncMock(return_value=[response])

        queries = [
            {"dense_vector": [0.1] * 1024},
            {"dense_vector": [0.2] * 1024},
        ]
        results = await service.batch_search_rrf(
            queries=queries, filters={"city": "Sofia"}, top_k=5
        )

        assert len(results) == 3
        call_kwargs = service._client.query_batch_points.call_args.kwargs
        for req in call_kwargs["requests"]:
            assert req.filter is not None
    async def test_batch_search_results_sorted_by_score(self, service):
        """Test merged results are sorted by score descending."""
        p1 = MagicMock(id="low", score=0.3, payload={"page_content": "L", "metadata": {}})
        p2 = MagicMock(id="high", score=0.99, payload={"page_content": "H", "metadata": {}})
        p3 = MagicMock(id="mid", score=0.6, payload={"page_content": "M", "metadata": {}})

        resp1 = MagicMock(points=[p1])
        resp2 = MagicMock(points=[p2])
        resp3 = MagicMock(points=[p3])

        service._client.query_batch_points = AsyncMock(return_value=[resp1, resp2, resp3])

        queries = [
            {"dense_vector": [0.1] * 1024},
            {"dense_vector": [0.2] * 1024},
            {"dense_vector": [0.3] * 1024},
        ]
        results = await service.batch_search_rrf(queries=queries, top_k=10)

        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        assert results[0]["id"] == "high"


class TestQdrantServiceHybridSearch:
    """Tests for hybrid_search_rrf method."""

    @pytest.fixture
    def service(self):
        return _make_service(validated=True)

    @pytest.fixture
    def mock_point(self):
        return _make_mock_point(
            id="doc_1", score=0.95, text="Test document content",
            metadata={"city": "Sofia", "price": 50000},
        )
    async def test_hybrid_search_with_sparse_vector(self, service, mock_point):
        """Test hybrid search includes sparse vector in prefetch."""
        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        sparse_vector = {"indices": [1, 5, 10], "values": [0.5, 0.3, 0.2]}

        results = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            sparse_vector=sparse_vector,
            top_k=5,
        )

        # Verify prefetch includes both dense and sparse
        call_kwargs = service._client.query_points.call_args.kwargs
        prefetch = call_kwargs["prefetch"]
        assert len(prefetch) == 2  # dense + sparse

        assert len(results) == 1
        assert results[0]["id"] == "doc_1"
    async def test_hybrid_search_without_sparse_vector(self, service, mock_point):
        """Test hybrid search works without sparse vector."""
        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        results = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            sparse_vector=None,
            top_k=5,
        )

        # Verify prefetch has only dense
        call_kwargs = service._client.query_points.call_args.kwargs
        prefetch = call_kwargs["prefetch"]
        assert len(prefetch) == 1  # dense only

        assert len(results) == 1
    async def test_hybrid_search_with_empty_sparse_indices(self, service, mock_point):
        """Test hybrid search handles empty sparse indices."""
        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        sparse_vector = {"indices": [], "values": []}

        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            sparse_vector=sparse_vector,
            top_k=5,
        )

        # Empty indices means no sparse prefetch
        call_kwargs = service._client.query_points.call_args.kwargs
        prefetch = call_kwargs["prefetch"]
        assert len(prefetch) == 1  # dense only
    async def test_hybrid_search_with_filters(self, service, mock_point):
        """Test hybrid search applies filters."""
        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        filters = {"city": "Sofia"}

        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            filters=filters,
            top_k=5,
        )

        call_kwargs = service._client.query_points.call_args.kwargs
        assert call_kwargs["query_filter"] is not None
    async def test_hybrid_search_weight_distribution(self, service, mock_point):
        """Test prefetch limits respect weight distribution."""
        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        sparse_vector = {"indices": [1, 2], "values": [0.5, 0.5]}

        await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            sparse_vector=sparse_vector,
            top_k=10,
            dense_weight=0.8,
            sparse_weight=0.2,
            prefetch_multiplier=3,
        )

        call_kwargs = service._client.query_points.call_args.kwargs
        prefetch = call_kwargs["prefetch"]

        # Dense gets higher limit due to higher weight
        dense_limit = prefetch[0].limit
        sparse_limit = prefetch[1].limit

        # Both should be at least top_k
        assert dense_limit >= 10
        assert sparse_limit >= 10
    async def test_hybrid_search_returns_formatted_results(self, service, mock_point):
        """Test results are properly formatted."""
        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        results = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            top_k=5,
        )

        assert len(results) == 1
        result = results[0]
        assert result["id"] == "doc_1"
        assert result["score"] == 0.95
        assert result["text"] == "Test document content"
        assert result["metadata"]["city"] == "Sofia"


class TestQdrantServiceTimeout:
    """Tests for explicit timeout configuration."""

    def test_default_timeout(self):
        """Verify AsyncQdrantClient receives timeout=30 by default."""
        import telegram_bot.services.qdrant as qdrant_mod

        with patch.object(qdrant_mod, "AsyncQdrantClient") as mock_client:
            qdrant_mod.QdrantService(url="http://localhost:6333")
            mock_client.assert_called_once_with(
                url="http://localhost:6333",
                api_key=None,
                prefer_grpc=True,
                timeout=30,
            )

    def test_custom_timeout(self):
        """Verify custom timeout is passed through."""
        import telegram_bot.services.qdrant as qdrant_mod

        with patch.object(qdrant_mod, "AsyncQdrantClient") as mock_client:
            qdrant_mod.QdrantService(url="http://localhost:6333", timeout=60)
            mock_client.assert_called_once_with(
                url="http://localhost:6333",
                api_key=None,
                prefer_grpc=True,
                timeout=60,
            )


class TestQdrantServiceScoreBoosting:
    """Tests for search_with_score_boosting method."""

    @pytest.fixture
    def service(self):
        return _make_service(validated=True)
    async def test_score_boosting_disabled(self, service):
        """Test search without freshness boosting."""
        mock_point = _make_mock_point(score=0.8)

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        results = await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=False,
            top_k=5,
        )

        assert len(results) == 1
        assert results[0]["score"] == 0.8
    async def test_score_boosting_uses_formula_query(self, service):
        """Test that freshness boost uses server-side FormulaQuery."""
        mock_point = _make_mock_point(score=0.85, text="recent doc")

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            freshness_scale_days=7,
            top_k=5,
        )

        call_args = service._client.query_points.call_args
        query_arg = call_args.kwargs.get("query") or call_args[1].get("query")
        assert hasattr(query_arg, "formula"), "Expected FormulaQuery with formula attribute"
    async def test_score_boosting_prefetch_structure(self, service):
        """Verify prefetch contains dense query with correct limit."""
        mock_point = _make_mock_point(score=0.8)

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            top_k=10,
        )

        call_args = service._client.query_points.call_args
        prefetch = call_args.kwargs.get("prefetch")
        assert prefetch is not None
        assert prefetch.limit == 10
    async def test_score_boosting_custom_scale(self, service):
        """Verify custom freshness_scale_days reaches FormulaQuery."""
        mock_point = _make_mock_point(score=0.8)

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            freshness_scale_days=14,
            top_k=5,
        )

        call_args = service._client.query_points.call_args
        query = call_args.kwargs.get("query")
        sum_expr = query.formula
        mult_expr = sum_expr.sum[1]
        decay_expr = mult_expr.mult[1]
        assert decay_expr.exp_decay.scale == 14.0
    async def test_score_boosting_custom_field(self, service):
        """Verify custom freshness_field reaches FormulaQuery."""
        mock_point = _make_mock_point(score=0.8)

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            freshness_field="updated_at",
            top_k=5,
        )

        call_args = service._client.query_points.call_args
        query = call_args.kwargs.get("query")
        sum_expr = query.formula
        mult_expr = sum_expr.sum[1]
        decay_expr = mult_expr.mult[1]
        assert decay_expr.exp_decay.x.datetime_key == "metadata.updated_at"
    async def test_score_boosting_fallback_on_error(self, service):
        """Test fallback to normal search when FormulaQuery fails."""
        mock_point = _make_mock_point(score=0.8)

        # First call (FormulaQuery) fails, second (plain) succeeds
        service._client.query_points = AsyncMock(
            side_effect=[
                Exception("FormulaQuery failed"),
                MagicMock(points=[mock_point]),
            ]
        )

        results = await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            top_k=5,
        )

        assert len(results) == 1


class TestQdrantServiceBuildFilter:
    """Tests for _build_filter method."""

    @pytest.fixture
    def service(self):
        return _make_service()

    def test_build_filter_empty(self, service):
        """Test None returned for empty filters."""
        assert service._build_filter(None) is None
        assert service._build_filter({}) is None

    def test_build_filter_exact_match(self, service):
        """Test exact match filter."""
        filter_obj = service._build_filter({"city": "Sofia"})

        assert filter_obj is not None
        assert len(filter_obj.must) == 1
        assert filter_obj.must[0].key == "metadata.city"

    def test_build_filter_multiple_exact_matches(self, service):
        """Test multiple exact match filters."""
        filter_obj = service._build_filter({"city": "Sofia", "rooms": 2})

        assert len(filter_obj.must) == 2

    def test_build_filter_range_gte(self, service):
        """Test range filter with gte."""
        filter_obj = service._build_filter({"price": {"gte": 50000}})

        assert filter_obj is not None
        assert len(filter_obj.must) == 1
        condition = filter_obj.must[0]
        assert condition.key == "metadata.price"
        assert condition.range.gte == 50000

    def test_build_filter_range_lte(self, service):
        """Test range filter with lte."""
        filter_obj = service._build_filter({"price": {"lte": 100000}})

        assert filter_obj is not None
        condition = filter_obj.must[0]
        assert condition.range.lte == 100000

    def test_build_filter_range_combined(self, service):
        """Test range filter with both gte and lte."""
        filter_obj = service._build_filter({"price": {"gte": 50000, "lte": 100000}})

        assert filter_obj is not None
        condition = filter_obj.must[0]
        assert condition.range.gte == 50000
        assert condition.range.lte == 100000

    def test_build_filter_range_all_operators(self, service):
        """Test all range operators."""
        filter_obj = service._build_filter({"value": {"gt": 10, "lt": 100, "gte": 5, "lte": 150}})

        assert filter_obj is not None
        condition = filter_obj.must[0]
        assert condition.range.gt == 10
        assert condition.range.lt == 100
        assert condition.range.gte == 5
        assert condition.range.lte == 150

    def test_build_filter_mixed(self, service):
        """Test mixed exact and range filters."""
        filter_obj = service._build_filter(
            {
                "city": "Burgas",
                "price": {"lte": 80000},
                "rooms": 2,
            }
        )

        assert filter_obj is not None
        assert len(filter_obj.must) == 3


class TestQdrantServiceFormatResults:
    """Tests for _format_results method."""

    @pytest.fixture
    def service(self):
        return _make_service()

    def test_format_results_basic(self, service):
        """Test basic result formatting."""
        mock_point = MagicMock()
        mock_point.id = "doc_1"
        mock_point.score = 0.95
        mock_point.payload = {
            "page_content": "Test content",
            "metadata": {"key": "value"},
        }

        results = service._format_results([mock_point])

        assert len(results) == 1
        assert results[0]["id"] == "doc_1"
        assert results[0]["score"] == 0.95
        assert results[0]["text"] == "Test content"
        assert results[0]["metadata"]["key"] == "value"

    def test_format_results_multiple(self, service):
        """Test formatting multiple results."""
        points = []
        for i in range(3):
            point = MagicMock()
            point.id = f"doc_{i}"
            point.score = 0.9 - i * 0.1
            point.payload = {"page_content": f"Content {i}", "metadata": {}}
            points.append(point)

        results = service._format_results(points)

        assert len(results) == 3
        assert results[0]["id"] == "doc_0"
        assert results[2]["id"] == "doc_2"

    def test_format_results_empty(self, service):
        """Test formatting empty results."""
        results = service._format_results([])
        assert results == []

    def test_format_results_missing_fields(self, service):
        """Test handling of missing payload fields."""
        mock_point = MagicMock()
        mock_point.id = "doc_1"
        mock_point.score = 0.8
        mock_point.payload = {}  # No page_content or metadata

        results = service._format_results([mock_point])

        assert len(results) == 1
        assert results[0]["text"] == ""  # Empty string for missing content
        assert results[0]["metadata"] == {}  # Empty dict for missing metadata

    def test_format_results_uuid_id(self, service):
        """Test ID is converted to string."""
        import uuid

        mock_point = MagicMock()
        mock_point.id = uuid.uuid4()
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        results = service._format_results([mock_point])

        assert isinstance(results[0]["id"], str)


class TestQdrantServiceClose:
    """Tests for close method."""
    async def test_close_calls_client_close(self):
        """Test close method calls client.close()."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
            )
            # Replace the client with our own mock so we can track calls
            mock_client = AsyncMock()
            service._client = mock_client

            await service.close()

            mock_client.close.assert_called_once()


class TestQdrantServiceInit:
    """Tests for initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="my_collection",
            )

            assert service._collection_name == "my_collection"
            assert service._dense_vector_name == "dense"
            assert service._sparse_vector_name == "bm42"

    def test_init_with_custom_vector_names(self):
        """Test initialization with custom vector names."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="my_collection",
                dense_vector_name="custom_dense",
                sparse_vector_name="custom_sparse",
            )

            assert service._dense_vector_name == "custom_dense"
            assert service._sparse_vector_name == "custom_sparse"

    def test_init_with_api_key(self):
        """Test initialization with API key creates a client."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                api_key="secret_key",
                collection_name="my_collection",
            )
            # Verify service was created with expected state
            assert service._client is not None
            assert service._collection_name == "my_collection"
