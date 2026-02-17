"""Tests for QdrantService with Query API, Score Boosting, MMR, and Quantization Mode."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_qdrant_client():
    """Create a mocked AsyncQdrantClient."""
    mock_client = AsyncMock()
    mock_client.query_points.return_value = MagicMock(points=[])
    mock_client.get_collection.return_value = MagicMock(
        points_count=100,
        vectors_count=100,
        status=MagicMock(value="green"),
    )
    _mc = MagicMock()
    _mc.name = "test"
    mock_client.get_collections.return_value = MagicMock(collections=[_mc])
    mock_client.close.return_value = None
    return mock_client


# =============================================================================
# TestQdrantServiceInit - Initialization and quantization_mode
# =============================================================================


class TestQdrantServiceInit:
    """Tests for QdrantService initialization."""

    def test_default_quantization_mode_off(self):
        """Test default quantization_mode is 'off'."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            assert service._quantization_mode == "off"

    def test_quantization_mode_binary(self):
        """Test service can be created with binary quantization mode."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                quantization_mode="binary",
            )

            assert service._quantization_mode == "binary"
            assert service._collection_name == "test_binary"

    def test_quantization_mode_scalar(self):
        """Test service can be created with scalar quantization mode."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                quantization_mode="scalar",
            )

            assert service._quantization_mode == "scalar"
            assert service._collection_name == "test_scalar"

    def test_collection_name_suffix_stripped(self):
        """Test existing suffixes are stripped before applying new one."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test_binary",
                quantization_mode="scalar",
            )

            # Should strip _binary suffix, then add _scalar
            assert service._collection_name == "test_scalar"


# =============================================================================
# TestHybridSearchRRFQuantization - Per-call quantization A/B testing
# =============================================================================


class TestHybridSearchRRFQuantization:
    """Tests for per-call quantization parameters in hybrid_search_rrf."""

    @pytest.mark.asyncio
    async def test_search_with_quantization_ignore_true(self):
        """Test quantization_ignore=True skips quantization."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_col = MagicMock()
            mock_col.name = "test"
            mock_client.get_collections.return_value = MagicMock(collections=[mock_col])
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
                quantization_ignore=True,
            )

            call_kwargs = mock_client.query_points.call_args[1]
            assert call_kwargs["search_params"] is not None
            assert call_kwargs["search_params"].quantization.ignore is True

    @pytest.mark.asyncio
    async def test_search_with_quantization_ignore_false(self):
        """Test quantization_ignore=False forces quantization."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_col = MagicMock()
            mock_col.name = "test"
            mock_client.get_collections.return_value = MagicMock(collections=[mock_col])
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
                quantization_ignore=False,
                quantization_rescore=True,
                quantization_oversampling=2.0,
            )

            call_kwargs = mock_client.query_points.call_args[1]
            assert call_kwargs["search_params"] is not None
            assert call_kwargs["search_params"].quantization.ignore is False
            assert call_kwargs["search_params"].quantization.rescore is True
            assert call_kwargs["search_params"].quantization.oversampling == 2.0

    @pytest.mark.asyncio
    async def test_search_without_quantization_override(self):
        """Test quantization_ignore=None means no search_params quantization."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_col = MagicMock()
            mock_col.name = "test"
            mock_client.get_collections.return_value = MagicMock(collections=[mock_col])
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
                quantization_ignore=None,  # Default — no override
            )

            call_kwargs = mock_client.query_points.call_args[1]
            # No quantization override → search_params should be None
            assert call_kwargs.get("search_params") is None


# =============================================================================
# TestQdrantServiceUnit - Core functionality
# =============================================================================


class TestQdrantServiceUnit:
    """Unit tests for QdrantService (no actual Qdrant calls)."""

    def test_init_creates_async_client(self):
        """Test initialization creates AsyncQdrantClient with gRPC."""
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
                prefer_grpc=True,
                timeout=30,
            )
            assert service._collection_name == "test_collection"

    @pytest.mark.asyncio
    async def test_hybrid_search_rrf_builds_prefetch(self):
        """Test hybrid_search_rrf builds correct prefetch queries."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            _mc = MagicMock()
            _mc.name = "test"
            mock_client.get_collections.return_value = MagicMock(collections=[_mc])
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
            _mc = MagicMock()
            _mc.name = "test"
            mock_client.get_collections.return_value = MagicMock(collections=[_mc])
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
            _mc = MagicMock()
            _mc.name = "test"
            mock_client.get_collections.return_value = MagicMock(collections=[_mc])
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
            _mc = MagicMock()
            _mc.name = "test"
            mock_client.get_collections.return_value = MagicMock(collections=[_mc])
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

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            points = [
                {"id": "0", "score": 0.95, "text": "A", "metadata": {}},
                {"id": "1", "score": 0.90, "text": "B", "metadata": {}},
                {"id": "2", "score": 0.85, "text": "C", "metadata": {}},
            ]

            embeddings = [
                [1.0, 0.0, 0.0],
                [0.99, 0.1, 0.0],  # Very similar to 0
                [0.0, 1.0, 0.0],  # Different
            ]

            result = service.mmr_rerank(
                points=points,
                embeddings=embeddings,
                lambda_mult=0.5,
                top_k=2,
            )

            assert result[0]["id"] == "0"
            assert result[1]["id"] == "2"

    def test_mmr_rerank_with_high_lambda_prefers_relevance(self):
        """Test MMR with high lambda prefers relevance over diversity."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
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
                lambda_mult=1.0,
                top_k=2,
            )

            assert result[0]["id"] == "0"
            assert result[1]["id"] == "1"

    def test_mmr_rerank_returns_all_if_fewer_than_top_k(self):
        """Test MMR returns all points if fewer than top_k."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
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

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
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

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
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

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            assert service._build_filter({}) is None
            assert service._build_filter(None) is None
