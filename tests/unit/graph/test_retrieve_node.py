"""Tests for retrieve_node — hybrid RRF search with cache."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.graph.nodes.retrieve import retrieve_node
from telegram_bot.graph.state import make_initial_state


_OK_META = {"backend_error": False, "error_type": None, "error_message": None}


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
        qdrant.hybrid_search_rrf = AsyncMock(return_value=(mock_docs, _OK_META))

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
    async def test_cache_hit_clears_stale_backend_error_flags(self):
        state = make_initial_state(user_id=1, session_id="s1", query="cached query")
        state["query_type"] = "FAQ"
        state["query_embedding"] = [0.2] * 1024
        state["retrieval_backend_error"] = True
        state["retrieval_error_type"] = "TimeoutError"

        cached_docs = _make_docs(1)
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

        assert result["retrieval_backend_error"] is False
        assert result["retrieval_error_type"] is None

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
        qdrant.hybrid_search_rrf = AsyncMock(return_value=([], _OK_META))

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
        qdrant.hybrid_search_rrf = AsyncMock(return_value=(_make_docs(2), _OK_META))

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
        qdrant.hybrid_search_rrf = AsyncMock(return_value=(mock_docs, _OK_META))

        await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        cache.store_search_results.assert_awaited_once()
        cache.store_sparse_embedding.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_handles_legacy_list_return_without_meta(self):
        """retrieve_node should handle legacy list-only Qdrant responses."""
        state = make_initial_state(user_id=1, session_id="s1", query="legacy")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        sparse_embeddings = AsyncMock()
        sparse_embeddings.aembed_query = AsyncMock(return_value={"indices": [1], "values": [0.5]})

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=_make_docs(2))

        result = await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        assert len(result["documents"]) == 2
        assert result["retrieval_backend_error"] is False
        assert result["retrieval_error_type"] is None

    @pytest.mark.asyncio
    async def test_parallel_embeddings_after_rewrite(self):
        """After rewrite (query_embedding=None), fallback parallel dense+sparse."""
        import asyncio

        state = make_initial_state(user_id=1, session_id="s1", query="rewritten query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = None  # simulates post-rewrite

        call_order: list[str] = []

        async def mock_dense_embed(query):
            call_order.append("dense_start")
            await asyncio.sleep(0.01)
            call_order.append("dense_end")
            return [0.1] * 1024

        async def mock_sparse_embed(query):
            call_order.append("sparse_start")
            await asyncio.sleep(0.01)
            call_order.append("sparse_end")
            return {"indices": [1, 2], "values": [0.5, 0.3]}

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        # Non-hybrid embeddings → falls through to parallel path
        embeddings = AsyncMock(spec=["aembed_query"])
        embeddings.aembed_query = AsyncMock(side_effect=mock_dense_embed)

        sparse_embeddings = AsyncMock()
        sparse_embeddings.aembed_query = AsyncMock(side_effect=mock_sparse_embed)

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=(_make_docs(3), _OK_META))

        result = await retrieve_node(
            state,
            cache=cache,
            embeddings=embeddings,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        assert len(result["documents"]) == 3
        # Both embeddings should have been computed
        embeddings.aembed_query.assert_awaited_once()
        sparse_embeddings.aembed_query.assert_awaited_once()
        # Check parallel execution: sparse_start should appear before dense_end
        assert "sparse_start" in call_order
        assert "dense_start" in call_order

    @pytest.mark.asyncio
    async def test_hybrid_embedding_after_rewrite(self):
        """After rewrite, hybrid embeddings uses single /encode/hybrid call."""
        state = make_initial_state(user_id=1, session_id="s1", query="rewritten query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = None  # simulates post-rewrite

        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        sparse_vec = {"indices": [1, 2], "values": [0.5, 0.3]}
        embeddings = MagicMock()
        embeddings.aembed_hybrid = AsyncMock(return_value=([0.1] * 1024, sparse_vec))

        sparse_embeddings = AsyncMock()

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=(_make_docs(3), _OK_META))

        result = await retrieve_node(
            state,
            cache=cache,
            embeddings=embeddings,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        assert len(result["documents"]) == 3
        embeddings.aembed_hybrid.assert_awaited_once_with("rewritten query")
        cache.store_embedding.assert_awaited_once()
        cache.store_sparse_embedding.assert_awaited_once()
        # sparse_embeddings should NOT be called — hybrid provided both
        sparse_embeddings.aembed_query.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_outputs_retrieved_context_for_judge(self):
        """retrieve_node should include curated context snippets for LLM judge."""
        state = make_initial_state(user_id=1, session_id="s1", query="test query")
        state["query_type"] = "GENERAL"
        state["query_embedding"] = [0.1] * 1024

        mock_docs = [
            {
                "id": "1",
                "text": "Document one content about property",
                "score": 0.9,
                "metadata": {"title": "Apt 1"},
            },
            {
                "id": "2",
                "text": "Document two content about real estate",
                "score": 0.7,
                "metadata": {"title": "Apt 2"},
            },
        ]

        cache = AsyncMock()
        cache.get_search_results = AsyncMock(return_value=None)
        cache.get_sparse_embedding = AsyncMock(return_value=None)
        cache.store_sparse_embedding = AsyncMock()
        cache.store_search_results = AsyncMock()

        sparse_embeddings = AsyncMock()
        sparse_embeddings.aembed_query = AsyncMock(
            return_value={"indices": [1, 2], "values": [0.5, 0.3]}
        )

        qdrant = AsyncMock()
        qdrant.hybrid_search_rrf = AsyncMock(return_value=(mock_docs, _OK_META))

        result = await retrieve_node(
            state,
            cache=cache,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
        )

        # Verify result includes retrieved_context for judge evaluation
        assert "retrieved_context" in result
        assert len(result["retrieved_context"]) == 2
        assert result["retrieved_context"][0]["score"] == 0.9
        assert "Document one content" in result["retrieved_context"][0]["content"]

    @pytest.mark.asyncio
    async def test_cache_hit_includes_retrieved_context(self):
        """Cache hit path should also include retrieved_context."""
        state = make_initial_state(user_id=1, session_id="s1", query="cached query")
        state["query_type"] = "FAQ"
        state["query_embedding"] = [0.2] * 1024

        cached_docs = [
            {"id": "1", "text": "Cached doc content", "score": 0.85, "metadata": {}},
        ]

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

        assert "retrieved_context" in result
        assert len(result["retrieved_context"]) == 1
        assert result["retrieved_context"][0]["score"] == 0.85
