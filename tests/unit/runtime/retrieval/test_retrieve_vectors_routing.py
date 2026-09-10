"""ColBERT fact routing through ``_execute_qdrant_retrieval`` (#3461).

``QdrantService`` owns the ``colbert_applied`` / ``fallback_reason`` facts and
reports them in the search meta on every ColBERT success/fallback branch.
``_execute_qdrant_retrieval`` must consume those returned facts instead of
inferring application from method/query availability: a ColBERT attempt that
fell back to RRF (exception, empty result, unavailable vector, empty query)
reaches the pipeline as ``colbert_applied=False`` so the pipeline neither
claims ColBERT reranking happened nor suppresses the configured fallback
reranker.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.runtime.pipeline._retrieve import _execute_qdrant_retrieval
from src.runtime.qdrant.service import QdrantService


def _make_real_service() -> QdrantService:
    """Real QdrantService shell that runs both search methods without a backend."""
    service = QdrantService.__new__(QdrantService)
    service._base_collection_name = "unit-collection"
    service._collection_name = "unit-collection"
    service._requested_quantization_mode = "off"
    service._quantization_mode = "off"
    service._dense_vector_name = "dense"
    service._sparse_vector_name = "sparse"
    service._colbert_available = True
    service._collection_validated = True
    service._client = AsyncMock()
    return service


class _StubQdrant:
    """Qdrant double whose meta is fully caller-controlled."""

    def __init__(self, *, with_colbert_method: bool = True, meta: dict[str, Any]) -> None:
        self._meta = meta
        self.colbert_called = False
        self.rrf_called = False
        if with_colbert_method:
            self.hybrid_search_rrf_colbert = AsyncMock(side_effect=self._record_colbert)
        self.hybrid_search_rrf = AsyncMock(side_effect=self._record_rrf)

    def _record_colbert(self, **kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.colbert_called = True
        return (
            [{"id": "stub-1", "score": 0.9, "text": "stub", "metadata": {}}],
            self._meta,
        )

    def _record_rrf(self, **kwargs: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.rrf_called = True
        return (
            [{"id": "rrf-1", "score": 0.8, "text": "rrf", "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )


async def _run(qdrant: Any) -> tuple[list[dict[str, Any]], dict[str, Any], bool]:
    return await _execute_qdrant_retrieval(
        qdrant=qdrant,
        dense_vector=[0.1] * 8,
        sparse_vector=None,
        colbert_query=[[0.2] * 8] * 3,
        filters=None,
        top_k=5,
        dense_weight=0.6,
        sparse_weight=0.4,
    )


@pytest.mark.asyncio
async def test_fallback_facts_are_consumed_not_inferred_from_availability() -> None:
    """Meta saying ``colbert_applied=False`` wins over method-availability inference."""
    qdrant = _StubQdrant(
        meta={
            "backend_error": False,
            "error_type": None,
            "error_message": None,
            "colbert_applied": False,
            "fallback_reason": "colbert_error:RuntimeError",
        }
    )

    results, search_meta, colbert_applied = await _run(qdrant)

    assert qdrant.colbert_called is True
    assert [doc["id"] for doc in results] == ["stub-1"]
    assert search_meta["fallback_reason"] == "colbert_error:RuntimeError"
    assert colbert_applied is False


@pytest.mark.asyncio
async def test_applied_fact_true_is_consumed_from_meta() -> None:
    """Meta saying ``colbert_applied=True`` is passed through unchanged."""
    qdrant = _StubQdrant(
        meta={
            "backend_error": False,
            "error_type": None,
            "error_message": None,
            "colbert_applied": True,
        }
    )

    _results, _search_meta, colbert_applied = await _run(qdrant)

    assert colbert_applied is True


@pytest.mark.asyncio
async def test_without_colbert_method_routes_to_rrf_and_reports_not_applied() -> None:
    """Qdrant without a ColBERT method routes to RRF; no facts means not applied."""
    qdrant = _StubQdrant(with_colbert_method=False, meta={})

    results, search_meta, colbert_applied = await _run(qdrant)

    assert qdrant.rrf_called is True
    assert hasattr(qdrant, "hybrid_search_rrf_colbert") is False
    assert [doc["id"] for doc in results] == ["rrf-1"]
    assert search_meta.get("colbert_applied", False) is False
    assert colbert_applied is False


@pytest.mark.asyncio
async def test_real_service_colbert_exception_reports_not_applied() -> None:
    """End-to-end #3461 repro: real QdrantService ColBERT error + successful RRF."""
    service = _make_real_service()
    service._client.query_points = AsyncMock(side_effect=RuntimeError("colbert unavailable"))
    service.hybrid_search_rrf = AsyncMock(
        return_value=(
            [{"id": "fallback_1", "score": 0.9, "text": "fallback", "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    results, search_meta, colbert_applied = await _run(service)

    assert [doc["id"] for doc in results] == ["fallback_1"]
    assert search_meta["backend_error"] is False
    assert search_meta["colbert_applied"] is False
    assert search_meta["fallback_reason"] == "colbert_error:RuntimeError"
    assert colbert_applied is False


@pytest.mark.asyncio
async def test_real_service_empty_colbert_reports_not_applied() -> None:
    """End-to-end #3461 repro: empty ColBERT result + successful RRF fallback."""
    service = _make_real_service()
    service._client.query_points = AsyncMock(return_value=MagicMock(points=[]))
    service.hybrid_search_rrf = AsyncMock(
        return_value=(
            [{"id": "fallback_1", "score": 0.9, "text": "fallback", "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    results, search_meta, colbert_applied = await _run(service)

    assert [doc["id"] for doc in results] == ["fallback_1"]
    assert search_meta["backend_error"] is False
    assert search_meta["colbert_applied"] is False
    assert search_meta["fallback_reason"] == "colbert_empty"
    assert colbert_applied is False
