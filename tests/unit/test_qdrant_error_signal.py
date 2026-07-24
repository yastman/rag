"""Tests for Qdrant backend_error meta signal (#117).

Verifies that hybrid_search_rrf with return_meta=True distinguishes
backend failures from genuine empty search results.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse

from src.runtime.qdrant.service import QdrantService


_PATCH_TARGET = "src.runtime.qdrant.service.AsyncQdrantClient"


@pytest.fixture
def service():
    """Create QdrantService with mocked client."""
    with patch(_PATCH_TARGET):
        svc = QdrantService(
            url="http://localhost:6333",
            collection_name="test_collection",
        )
        svc._client = AsyncMock()
        svc._collection_validated = True
        return svc


class TestQdrantErrorSignal:
    """Test per-call backend_error meta from hybrid_search_rrf."""

    async def test_backend_exception_returns_error_meta(self, service):
        """Qdrant SDK exception -> backend_error=True, error_type filled."""
        service._client.query_points = AsyncMock(
            side_effect=ResponseHandlingException("connection reset")
        )

        results, meta = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            return_meta=True,
        )

        assert results == []
        assert meta["backend_error"] is True
        assert meta["error_type"] == "ResponseHandlingException"
        assert "connection reset" in meta["error_message"]

    async def test_empty_results_returns_no_error(self, service):
        """Genuine empty search -> backend_error=False."""
        service._client.query_points = AsyncMock(return_value=MagicMock(points=[]))

        results, meta = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            return_meta=True,
        )

        assert results == []
        assert meta["backend_error"] is False
        assert meta["error_type"] is None
        assert meta["error_message"] is None

    async def test_unexpected_response_returns_error_meta(self, service):
        """UnexpectedResponse exception -> backend_error=True."""
        import httpx

        service._client.query_points = AsyncMock(
            side_effect=UnexpectedResponse(
                status_code=503,
                reason_phrase="Service Unavailable",
                content=b"overloaded",
                headers=httpx.Headers(),
            )
        )

        results, meta = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            return_meta=True,
        )

        assert results == []
        assert meta["backend_error"] is True
        assert meta["error_type"] == "UnexpectedResponse"

    async def test_return_meta_false_preserves_old_contract(self, service):
        """Default return_meta=False returns list[dict] (backward compat)."""
        mock_point = MagicMock()
        mock_point.id = "1"
        mock_point.score = 0.9
        mock_point.payload = {"page_content": "test", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        result = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            return_meta=False,
        )

        # Old contract: plain list, not tuple
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "1"

    async def test_success_with_results_meta(self, service):
        """Successful search with results -> backend_error=False, results populated."""
        mock_point = MagicMock()
        mock_point.id = "doc_1"
        mock_point.score = 0.95
        mock_point.payload = {"page_content": "content", "metadata": {}}

        service._client.query_points = AsyncMock(return_value=MagicMock(points=[mock_point]))

        results, meta = await service.hybrid_search_rrf(
            dense_vector=[0.1] * 1024,
            return_meta=True,
        )

        assert len(results) == 1
        assert results[0]["id"] == "doc_1"
        assert meta["backend_error"] is False
        assert meta["error_type"] is None


class TestQdrantCollectionSafety:
    """Test strict-mode configuration and observable quantization fallback."""

    async def test_strict_mode_serializes_qdrant_1_18_guardrails(self, service):
        """SDK config carries the new server-side batch and memory limits."""
        await service._apply_strict_mode()

        strict_config = service._client.update_collection.await_args.kwargs["strict_mode_config"]

        assert strict_config.model_dump(exclude_none=True) == {
            "enabled": True,
            "max_query_limit": 100,
            "max_timeout": 30,
            "search_max_hnsw_ef": 512,
            "search_max_batchsize": 10,
            "max_resident_memory_percent": 80,
        }

    async def test_quantization_fallback_emits_metric_and_remains_visible(self):
        """Reindex fallback is observable instead of silently changing requested mode."""
        with patch(_PATCH_TARGET):
            service = QdrantService(
                url="http://localhost:6333",
                collection_name="test_collection",
                quantization_mode="binary",
            )
        service._client = AsyncMock()
        collection = MagicMock()
        collection.name = "test_collection"
        service._client.get_collections.return_value = MagicMock(collections=[collection])

        with patch("src.runtime.qdrant.service.record_pipeline_event") as record_event:
            await service.ensure_collection()

        assert service.collection_name == "test_collection"
        assert service.requested_quantization_mode == "binary"
        assert service.quantization_mode == "off"
        assert service.quantization_degraded is True
        record_event.assert_called_once_with("qdrant.quantization_fallback")
