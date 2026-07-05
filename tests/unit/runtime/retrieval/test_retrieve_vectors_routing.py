"""Q3: ColBERT/RRF routing in RetrievalService.retrieve_vectors.

Tests that RetrievalService routes to the correct Qdrant search method
based on whether a colbert_query is present in the VectorRetrievalRequest.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from src.runtime.retrieval.service import RetrievalService, VectorRetrievalRequest


_DENSE = [0.1] * 1024
_SPARSE = {"indices": [1, 2, 3], "values": [0.5, 0.3, 0.2]}
_COLBERT = [[0.1] * 128, [0.2] * 128]


def _make_qdrant_mock(*, has_colbert_method: bool = True) -> MagicMock:
    qdrant = MagicMock()
    qdrant.hybrid_search_rrf = AsyncMock(return_value=[{"id": "rrf-1", "score": 0.8}])
    if has_colbert_method:
        qdrant.hybrid_search_rrf_colbert = AsyncMock(
            return_value=[{"id": "colbert-1", "score": 0.9}]
        )
    else:
        # Simulate a qdrant that doesn't have the colbert method
        del qdrant.hybrid_search_rrf_colbert
    return qdrant


class TestRetrieveVectorsRouting:
    """RetrievalService.retrieve_vectors routes to ColBERT or RRF path."""

    async def test_colbert_query_set_routes_to_colbert_path(self):
        """When colbert_query is set and method exists → hybrid_search_rrf_colbert called."""
        qdrant = _make_qdrant_mock(has_colbert_method=True)
        svc = RetrievalService(qdrant=qdrant)

        request = VectorRetrievalRequest(
            dense_vector=_DENSE,
            sparse_vector=_SPARSE,
            colbert_query=_COLBERT,
            top_k=5,
        )
        result = await svc.retrieve_vectors(request)

        qdrant.hybrid_search_rrf_colbert.assert_awaited_once()
        qdrant.hybrid_search_rrf.assert_not_awaited()
        assert result == [{"id": "colbert-1", "score": 0.9}]

    async def test_colbert_query_none_routes_to_rrf_path(self):
        """When colbert_query is None → hybrid_search_rrf called."""
        qdrant = _make_qdrant_mock(has_colbert_method=True)
        svc = RetrievalService(qdrant=qdrant)

        request = VectorRetrievalRequest(
            dense_vector=_DENSE,
            sparse_vector=_SPARSE,
            colbert_query=None,
            top_k=5,
        )
        result = await svc.retrieve_vectors(request)

        qdrant.hybrid_search_rrf.assert_awaited_once()
        qdrant.hybrid_search_rrf_colbert.assert_not_awaited()
        assert result == [{"id": "rrf-1", "score": 0.8}]

    async def test_colbert_query_set_but_method_missing_routes_to_rrf(self):
        """colbert_query set but qdrant lacks the method → falls back to hybrid_search_rrf."""
        qdrant = _make_qdrant_mock(has_colbert_method=False)
        svc = RetrievalService(qdrant=qdrant)

        request = VectorRetrievalRequest(
            dense_vector=_DENSE,
            colbert_query=_COLBERT,
            top_k=5,
        )
        result = await svc.retrieve_vectors(request)

        qdrant.hybrid_search_rrf.assert_awaited_once()
        assert result == [{"id": "rrf-1", "score": 0.8}]

    async def test_colbert_path_forwards_colbert_query_kwarg(self):
        """colbert_query is forwarded as a keyword argument to hybrid_search_rrf_colbert."""
        qdrant = _make_qdrant_mock(has_colbert_method=True)
        svc = RetrievalService(qdrant=qdrant)

        request = VectorRetrievalRequest(
            dense_vector=_DENSE,
            sparse_vector=_SPARSE,
            colbert_query=_COLBERT,
            top_k=7,
        )
        await svc.retrieve_vectors(request)

        call_kwargs = qdrant.hybrid_search_rrf_colbert.call_args.kwargs
        assert call_kwargs["colbert_query"] == _COLBERT
        assert call_kwargs["dense_vector"] == _DENSE
        assert call_kwargs["top_k"] == 7

    async def test_rrf_path_does_not_receive_colbert_kwarg(self):
        """hybrid_search_rrf is NOT called with colbert_query argument."""
        qdrant = _make_qdrant_mock(has_colbert_method=True)
        svc = RetrievalService(qdrant=qdrant)

        request = VectorRetrievalRequest(
            dense_vector=_DENSE,
            colbert_query=None,
            top_k=3,
        )
        await svc.retrieve_vectors(request)

        call_kwargs = qdrant.hybrid_search_rrf.call_args.kwargs
        assert "colbert_query" not in call_kwargs
