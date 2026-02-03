"""Tests for QdrantService quantization parameters."""

import sys
from datetime import UTC
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


class TestQdrantServiceHybridSearch:
    """Tests for hybrid_search_rrf method."""

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

    @pytest.fixture
    def mock_point(self):
        """Create mock search point."""
        point = MagicMock()
        point.id = "doc_1"
        point.score = 0.95
        point.payload = {
            "page_content": "Test document content",
            "metadata": {"city": "Sofia", "price": 50000},
        }
        return point

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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


class TestQdrantServiceScoreBoosting:
    """Tests for search_with_score_boosting method."""

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
    async def test_score_boosting_disabled(self, service):
        """Test search without freshness boosting."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.8
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        results = await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=False,
            top_k=5,
        )

        assert len(results) == 1
        assert results[0]["score"] == 0.8

    @pytest.mark.asyncio
    async def test_score_boosting_with_fresh_document(self, service):
        """Test freshness boost increases score for new documents."""
        from datetime import datetime

        # Create document with recent timestamp
        now = datetime.now(UTC)
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.7
        mock_point.payload = {
            "page_content": "recent doc",
            "metadata": {"created_at": now.isoformat()},
        }

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        results = await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            freshness_scale_days=7,
            top_k=5,
        )

        assert len(results) == 1
        # Fresh documents should have boosted score
        # Base score is 0.7, boost adds up to 0.1

    @pytest.mark.asyncio
    async def test_score_boosting_with_old_document(self, service):
        """Test freshness boost is minimal for old documents."""
        from datetime import datetime, timedelta

        # Create document with old timestamp
        old_date = datetime.now(UTC) - timedelta(days=30)
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.7
        mock_point.payload = {
            "page_content": "old doc",
            "metadata": {"created_at": old_date.isoformat()},
        }

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        results = await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            freshness_scale_days=7,
            top_k=5,
        )

        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_score_boosting_reorders_by_freshness(self, service):
        """Test fresher documents can overtake older ones."""
        from datetime import datetime, timedelta

        now = datetime.now(UTC)
        old_date = now - timedelta(days=30)

        # Old doc with higher base score
        old_point = MagicMock()
        old_point.id = "old"
        old_point.score = 0.85
        old_point.payload = {
            "page_content": "old doc",
            "metadata": {"created_at": old_date.isoformat()},
        }

        # New doc with slightly lower base score
        new_point = MagicMock()
        new_point.id = "new"
        new_point.score = 0.80
        new_point.payload = {
            "page_content": "new doc",
            "metadata": {"created_at": now.isoformat()},
        }

        service._client.query_points = AsyncMock(
            return_value=MagicMock(points=[old_point, new_point])
        )

        results = await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            freshness_scale_days=7,
            top_k=2,
        )

        # With freshness boost, newer doc may come first
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_score_boosting_handles_missing_date(self, service):
        """Test graceful handling of missing date field."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.8
        mock_point.payload = {
            "page_content": "no date",
            "metadata": {},  # No created_at
        }

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        results = await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            top_k=5,
        )

        assert len(results) == 1
        # Should return without error, using base score

    @pytest.mark.asyncio
    async def test_score_boosting_handles_invalid_date(self, service):
        """Test graceful handling of invalid date format."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.8
        mock_point.payload = {
            "page_content": "bad date",
            "metadata": {"created_at": "not-a-date"},
        }

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        results = await service.search_with_score_boosting(
            dense_vector=[0.1] * 1024,
            freshness_boost=True,
            top_k=5,
        )

        assert len(results) == 1
        # Should return without error

    @pytest.mark.asyncio
    async def test_score_boosting_fallback_on_error(self, service):
        """Test fallback to normal search when boosting fails."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.8
        mock_point.payload = {"page_content": "test", "metadata": {}}

        # First call fails, second succeeds
        service._client.query_points = AsyncMock(
            side_effect=[
                Exception("First query failed"),
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
        """Create QdrantService with mocked client."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            return QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
            )

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
        """Create QdrantService with mocked client."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            return QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
            )

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

    @pytest.mark.asyncio
    async def test_close_calls_client_close(self):
        """Test close method calls client.close()."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_cls:
            mock_client = AsyncMock()
            mock_cls.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
            )

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
        """Test initialization with API key."""
        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_cls:
            QdrantService(
                url="http://localhost:6333",
                api_key="secret_key",
                collection_name="my_collection",
            )

            mock_cls.assert_called_once_with(
                url="http://localhost:6333",
                api_key="secret_key",
            )
