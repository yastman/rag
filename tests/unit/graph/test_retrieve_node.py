"""Tests for retrieve_node — hybrid RRF search with cache."""

from unittest.mock import AsyncMock

import pytest

from telegram_bot.graph.nodes.retrieve import retrieve_node
from telegram_bot.graph.state import make_initial_state


def _make_docs(n: int = 3) -> list[dict]:
    """Create mock search results."""
    return [
        {"id": str(i), "text": f"Document {i} content", "score": 0.9 - i * 0.1, "metadata": {}}
        for i in range(n)
    ]


class TestRetrieveNode:
    """Test retrieve_node."""

    @pytest.mark.asyncio
    async def test_returns_documents(self):
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024

        mock_docs = _make_docs(5)

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        sparse_embeddings = AsyncMock()
        sparse_embeddings.aembed_query = AsyncMock(
            return_value={"indices": [1, 2, 3], "values": [0.5, 0.3, 0.1]}
        )

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=mock_docs)

        result = await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        assert len(result["documents"]) == 5
        assert result["search_results_count"] == 5
        qdrant.hybrid_search_rrf.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_uses_cached_search(self):
        state = make_initial_state(user_id=1, session_id="s1", query="cached query")
        state["query_type"] = "FAQ"
        state["query_embedding"] = [0.2] * 1024

        cached_docs = _make_docs(3)

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=cached_docs)

        qdrant = AsyncMock()
        sparse_embeddings = AsyncMock()

        result = await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        assert len(result["documents"]) == 3
        assert result["search_results_count"] == 3
        # Qdrant should NOT be called — we used cache
        qdrant.hybrid_search_rrf.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_handles_empty_results(self):
        state = make_initial_state(user_id=1, session_id="s1", query="obscure query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.3] * 1024

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        sparse_embeddings = AsyncMock()
        sparse_embeddings.aembed_query = AsyncMock(return_value={"indices": [1], "values": [0.1]})

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=[])

        result = await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        assert result["documents"] == []
        assert result["search_results_count"] == 0

    @pytest.mark.asyncio
    async def test_uses_cached_sparse_embedding(self):
        state = make_initial_state(user_id=1, session_id="s1", query="test")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024

        cached_sparse = {"indices": [10, 20], "values": [0.8, 0.6]}

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=cached_sparse)
        cache.store_search_results = AsyncMock()

        sparse_embeddings = AsyncMock()
        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=_make_docs(2))

        await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        # Should NOT compute sparse — used cached
        sparse_embeddings.aembed_query.assert_not_awaited()
        # Qdrant should be called with cached sparse
        call_kwargs = qdrant.hybrid_search_rrf.call_args[1]
        assert call_kwargs["sparse_vector"] == cached_sparse

    @pytest.mark.asyncio
    async def test_stores_results_in_cache(self):
        state = make_initial_state(user_id=1, session_id="s1", query="cache me")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024

        mock_docs = _make_docs(3)

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        sparse_embeddings = AsyncMock()
        sparse_embeddings.aembed_query = AsyncMock(return_value={"indices": [1], "values": [0.5]})

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=mock_docs)

        await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        cache.store_search_results.assert_awaited_once()
        cache.store_sparse_embedding.assert_awaited_once()
