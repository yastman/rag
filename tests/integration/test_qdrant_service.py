"""Tests for QdrantService with Query API, Score Boosting, MMR, and Binary Quantization."""

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
    mock_client.update_collection.return_value = None
    mock_client.get_collection.return_value = MagicMock(
        points_count=100,
        vectors_count=100,
        status=MagicMock(value="green"),
        config=MagicMock(quantization_config=None),
    )
    mock_client.close.return_value = None
    return mock_client


@pytest.fixture
def qdrant_service(mock_qdrant_client):
    """Create QdrantService with mocked client."""
    with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
        mock_class.return_value = mock_qdrant_client
        from telegram_bot.services.qdrant import QdrantService

        service = QdrantService(
            url="http://localhost:6333",
            api_key="test-key",
            collection_name="test_collection",
        )
        # Expose mock for assertions
        service._mock_client = mock_qdrant_client
        yield service


# =============================================================================
# TestQdrantServiceInit - Initialization and Quantization Defaults
# =============================================================================


class TestQdrantServiceInit:
    """Tests for QdrantService initialization and quantization settings."""

    def test_default_quantization_enabled(self):
        """Test default quantization parameters are True, True, 2.0."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            assert service._use_quantization is True
            assert service._quantization_rescore is True
            assert service._quantization_oversampling == 2.0

    def test_quantization_disabled(self):
        """Test service can be created with quantization disabled."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                use_quantization=False,
            )

            assert service._use_quantization is False

    def test_custom_quantization_params(self):
        """Test service accepts custom quantization parameters."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                use_quantization=True,
                quantization_rescore=False,
                quantization_oversampling=3.0,
            )

            assert service._use_quantization is True
            assert service._quantization_rescore is False
            assert service._quantization_oversampling == 3.0


# =============================================================================
# TestHybridSearchRRFQuantization - Quantization in hybrid search
# =============================================================================


class TestHybridSearchRRFQuantization:
    """Tests for quantization parameters in hybrid_search_rrf."""
    async def test_search_with_quantization_enabled(self):
        """Test quantization params are passed when enabled (default)."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                use_quantization=True,
                quantization_rescore=True,
                quantization_oversampling=2.0,
            )

            await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
            )

            call_kwargs = mock_client.query_points.call_args[1]

            # Verify search_params has quantization config
            assert call_kwargs["search_params"] is not None
            quant_params = call_kwargs["search_params"].quantization
            assert quant_params.ignore is False  # Use quantization
            assert quant_params.rescore is True
            assert quant_params.oversampling == 2.0
    async def test_search_with_quantization_disabled_at_init(self):
        """Test no quantization params when disabled at service init."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                use_quantization=False,
            )

            await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
            )

            call_kwargs = mock_client.query_points.call_args[1]
            # Should not have search_params when quantization disabled
            assert call_kwargs["search_params"] is None
    async def test_search_with_quantization_ignore_true(self):
        """Test A/B testing: quantization_ignore=True skips quantization."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_class.return_value = mock_client

            # Service has quantization enabled by default
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                use_quantization=True,
            )

            # But we override per-request to ignore quantization
            await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
                quantization_ignore=True,  # A/B test: skip quantization
            )

            call_kwargs = mock_client.query_points.call_args[1]

            # Should have search_params with ignore=True
            assert call_kwargs["search_params"] is not None
            assert call_kwargs["search_params"].quantization.ignore is True
    async def test_search_with_quantization_ignore_false(self):
        """Test A/B testing: quantization_ignore=False forces quantization."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_class.return_value = mock_client

            # Service has quantization disabled
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                use_quantization=False,
            )

            # But we override per-request to force quantization
            await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
                quantization_ignore=False,  # A/B test: force quantization
            )

            call_kwargs = mock_client.query_points.call_args[1]

            # Should have search_params with quantization enabled
            assert call_kwargs["search_params"] is not None
            assert call_kwargs["search_params"].quantization.ignore is False
    async def test_search_with_quantization_ignore_none_uses_default(self):
        """Test quantization_ignore=None uses service default."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.query_points.return_value = MagicMock(points=[])
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
                use_quantization=True,
                quantization_oversampling=4.0,  # Custom value
            )

            await service.hybrid_search_rrf(
                dense_vector=[0.1] * 1024,
                top_k=10,
                quantization_ignore=None,  # Use default
            )

            call_kwargs = mock_client.query_points.call_args[1]

            # Should use service defaults
            assert call_kwargs["search_params"].quantization.oversampling == 4.0


# =============================================================================
# TestBinaryQuantization - enable_binary_quantization and get_collection_info
# =============================================================================


class TestBinaryQuantization:
    """Tests for binary quantization management methods."""
    async def test_enable_binary_quantization_success(self):
        """Test enable_binary_quantization returns True on success."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.update_collection.return_value = None  # Success
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
            )

            result = await service.enable_binary_quantization()

            assert result is True
            mock_client.update_collection.assert_called_once()
            call_kwargs = mock_client.update_collection.call_args[1]
            assert call_kwargs["collection_name"] == "test_collection"
            assert call_kwargs["quantization_config"] is not None
    async def test_enable_binary_quantization_custom_collection(self):
        """Test enable_binary_quantization works with custom collection name."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.update_collection.return_value = None
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="default_collection",
            )

            result = await service.enable_binary_quantization(collection_name="custom_collection")

            assert result is True
            call_kwargs = mock_client.update_collection.call_args[1]
            assert call_kwargs["collection_name"] == "custom_collection"
    async def test_enable_binary_quantization_always_ram_false(self):
        """Test enable_binary_quantization with always_ram=False."""
        from qdrant_client import models

        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.update_collection.return_value = None
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            result = await service.enable_binary_quantization(always_ram=False)

            assert result is True
            call_kwargs = mock_client.update_collection.call_args[1]
            # Verify BinaryQuantization config
            quant_config = call_kwargs["quantization_config"]
            assert isinstance(quant_config, models.BinaryQuantization)
    async def test_enable_binary_quantization_failure(self):
        """Test enable_binary_quantization returns False on failure."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.update_collection.side_effect = Exception("Connection failed")
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            result = await service.enable_binary_quantization()

            assert result is False
    async def test_get_collection_info_success(self):
        """Test get_collection_info returns correct dict."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_info = MagicMock()
            mock_info.points_count = 1000
            mock_info.vectors_count = 1000
            mock_info.status.value = "green"
            mock_info.config.quantization_config = MagicMock()
            mock_info.config.quantization_config.__str__ = lambda _: "BinaryQuantization"
            mock_client.get_collection.return_value = mock_info
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
            )

            result = await service.get_collection_info()

            assert result["name"] == "test_collection"
            assert result["points_count"] == 1000
            assert result["vectors_count"] == 1000
            assert result["status"] == "green"
            assert result["quantization"] is not None
    async def test_get_collection_info_custom_collection(self):
        """Test get_collection_info with custom collection name."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_info = MagicMock()
            mock_info.points_count = 500
            mock_info.vectors_count = 500
            mock_info.status.value = "yellow"
            mock_info.config.quantization_config = None
            mock_client.get_collection.return_value = mock_info
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="default",
            )

            result = await service.get_collection_info(collection_name="other_collection")

            assert result["name"] == "other_collection"
            assert result["quantization"] is None
            mock_client.get_collection.assert_called_once_with(collection_name="other_collection")
    async def test_get_collection_info_failure(self):
        """Test get_collection_info returns empty dict on failure."""
        from telegram_bot.services.qdrant import QdrantService

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient") as mock_class:
            mock_client = AsyncMock()
            mock_client.get_collection.side_effect = Exception("Collection not found")
            mock_class.return_value = mock_client

            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test",
            )

            result = await service.get_collection_info()

            assert result == {}


# =============================================================================
# Original tests (TestQdrantServiceUnit)
# =============================================================================


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

        with patch("telegram_bot.services.qdrant.AsyncQdrantClient"):
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
                lambda_mult=1.0,  # Only relevance
                top_k=2,
            )

            # Should select by score only: 0, then 1
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
