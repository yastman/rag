"""Tests for telegram_bot.services.rag_core — shared RAG core functions.

TDD: tests written BEFORE implementation.  All tests will initially fail with
ImportError (module doesn't exist yet) — that's the expected RED state.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.rag_core import (
    CACHEABLE_QUERY_TYPES,
    build_retrieved_context,
    check_semantic_cache,
    compute_query_embedding,
    perform_rerank,
    rewrite_query_via_llm,
)


# ---------------------------------------------------------------------------
# H2: build_retrieved_context
# ---------------------------------------------------------------------------


class TestBuildRetrievedContext:
    """Tests for build_retrieved_context — identical in both pipeline files."""

    def test_empty_list_returns_empty(self):
        assert build_retrieved_context([]) == []

    def test_extracts_text_score_and_chunk_location(self):
        docs = [
            {"text": "hello world", "score": 0.85, "metadata": {"chunk_location": "doc/p1"}},
        ]
        result = build_retrieved_context(docs)
        assert len(result) == 1
        assert result[0]["content"] == "hello world"
        assert result[0]["score"] == 0.85
        assert result[0]["chunk_location"] == "doc/p1"

    def test_respects_limit(self):
        docs = [{"text": f"doc {i}", "score": 0.1 * i, "metadata": {}} for i in range(10)]
        result = build_retrieved_context(docs, limit=3)
        assert len(result) == 3

    def test_default_limit_is_five(self):
        docs = [{"text": f"doc {i}", "score": 0.1, "metadata": {}} for i in range(10)]
        result = build_retrieved_context(docs)
        assert len(result) == 5

    def test_skips_non_dict_entries(self):
        docs = [
            "not a dict",
            {"text": "valid", "score": 0.5, "metadata": {}},
        ]
        result = build_retrieved_context(docs)
        assert len(result) == 1
        assert result[0]["content"] == "valid"

    def test_truncates_text_to_500_chars(self):
        long_text = "x" * 600
        docs = [{"text": long_text, "score": 0.5, "metadata": {}}]
        result = build_retrieved_context(docs)
        assert len(result[0]["content"]) == 500

    def test_missing_metadata_uses_empty_string_for_chunk_location(self):
        docs = [{"text": "content", "score": 0.7}]
        result = build_retrieved_context(docs)
        assert result[0]["chunk_location"] == ""


# ---------------------------------------------------------------------------
# H4: rewrite_query_via_llm
# ---------------------------------------------------------------------------


def _make_llm_response(content: str, model: str = "gpt-4o") -> MagicMock:
    """Create a mock LLM response object matching OpenAI-compatible API."""
    response = MagicMock()
    response.choices[0].message.content = content
    response.model = model
    return response


class TestRewriteQueryViaLlm:
    """Tests for rewrite_query_via_llm core function."""

    async def test_successful_rewrite_returns_new_query(self, monkeypatch):
        llm = MagicMock()
        llm.chat.completions.create = AsyncMock(
            return_value=_make_llm_response("квартира с балконом", model="gpt-4o")
        )

        monkeypatch.setenv("REWRITE_MODEL", "gpt-4o")
        monkeypatch.setenv("REWRITE_MAX_TOKENS", "200")

        rewritten, effective, model = await rewrite_query_via_llm("балкон квартира", llm=llm)

        assert rewritten == "квартира с балконом"
        assert effective is True
        assert model == "gpt-4o"

    async def test_same_as_original_marks_not_effective(self, monkeypatch):
        original = "двухкомнатная квартира"
        llm = MagicMock()
        llm.chat.completions.create = AsyncMock(
            return_value=_make_llm_response(original, model="gpt-4o")
        )

        monkeypatch.setenv("REWRITE_MODEL", "gpt-4o")
        monkeypatch.setenv("REWRITE_MAX_TOKENS", "200")

        rewritten, effective, _ = await rewrite_query_via_llm(original, llm=llm)

        assert rewritten == original
        assert effective is False

    async def test_empty_llm_response_keeps_original(self, monkeypatch):
        original = "студия у моря"
        llm = MagicMock()
        llm.chat.completions.create = AsyncMock(return_value=_make_llm_response("", model="gpt-4o"))

        monkeypatch.setenv("REWRITE_MODEL", "gpt-4o")
        monkeypatch.setenv("REWRITE_MAX_TOKENS", "200")

        rewritten, effective, _ = await rewrite_query_via_llm(original, llm=llm)

        assert rewritten == original
        assert effective is False

    async def test_llm_error_raises_exception(self, monkeypatch):
        llm = MagicMock()
        llm.chat.completions.create = AsyncMock(side_effect=ConnectionError("LLM unavailable"))

        monkeypatch.setenv("REWRITE_MODEL", "gpt-4o")
        monkeypatch.setenv("REWRITE_MAX_TOKENS", "200")

        with pytest.raises(ConnectionError, match="LLM unavailable"):
            await rewrite_query_via_llm("test query", llm=llm)


# ---------------------------------------------------------------------------
# H3: perform_rerank
# ---------------------------------------------------------------------------


class TestPerformRerank:
    """Tests for perform_rerank core function."""

    async def test_empty_documents_returns_empty(self):
        docs, applied, cache_hit = await perform_rerank(
            "query", [], cache=None, reranker=None, top_k=3
        )
        assert docs == []
        assert applied is False
        assert cache_hit is False

    async def test_no_reranker_returns_documents_unchanged(self):
        """Without reranker, returns all docs unmodified; callers sort/trim."""
        documents = [
            {"text": "doc1", "score": 0.5},
            {"text": "doc2", "score": 0.9},
            {"text": "doc3", "score": 0.7},
        ]
        docs, applied, cache_hit = await perform_rerank(
            "query", documents, cache=None, reranker=None, top_k=2
        )
        assert docs == documents  # unchanged, caller's responsibility to sort
        assert applied is False
        assert cache_hit is False

    async def test_reranker_cache_hit_skips_rerank_call(self):
        documents = [{"text": "doc1", "score": 0.5}]
        cached = [{"text": "doc1", "score": 0.95}]

        cache = AsyncMock()
        cache.get_rerank_results = AsyncMock(return_value=cached)
        reranker = AsyncMock()

        docs, applied, cache_hit = await perform_rerank(
            "query", documents, cache=cache, reranker=reranker, top_k=3
        )

        assert docs == cached
        assert applied is True
        assert cache_hit is True
        reranker.rerank.assert_not_awaited()

    async def test_reranker_success_returns_reranked_docs(self):
        documents = [
            {"text": "doc0", "score": 0.5},
            {"text": "doc1", "score": 0.6},
            {"text": "doc2", "score": 0.7},
        ]
        rerank_results = [
            {"index": 2, "score": 0.98},
            {"index": 0, "score": 0.85},
        ]

        cache = AsyncMock()
        cache.get_rerank_results = AsyncMock(return_value=None)
        cache.store_rerank_results = AsyncMock()
        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=rerank_results)

        docs, applied, cache_hit = await perform_rerank(
            "query", documents, cache=cache, reranker=reranker, top_k=2
        )

        assert len(docs) == 2
        assert docs[0]["text"] == "doc2"  # index=2
        assert docs[0]["score"] == 0.98
        assert docs[1]["text"] == "doc0"  # index=0
        assert docs[1]["score"] == 0.85
        assert applied is True
        assert cache_hit is False
        cache.store_rerank_results.assert_awaited_once()

    async def test_reranker_error_propagates_to_caller(self):
        """Reranker errors propagate so callers can log spans and do fallback."""
        documents = [
            {"text": "doc1", "score": 0.5},
            {"text": "doc2", "score": 0.9},
        ]

        cache = AsyncMock()
        cache.get_rerank_results = AsyncMock(return_value=None)
        reranker = AsyncMock()
        reranker.rerank = AsyncMock(side_effect=RuntimeError("reranker unavailable"))

        with pytest.raises(RuntimeError, match="reranker unavailable"):
            await perform_rerank("query", documents, cache=cache, reranker=reranker, top_k=2)

    async def test_no_cache_skips_rerank_cache_operations(self):
        """When cache=None, reranker works without caching."""
        documents = [{"text": "doc0", "score": 0.5}]
        rerank_results = [{"index": 0, "score": 0.9}]

        reranker = AsyncMock()
        reranker.rerank = AsyncMock(return_value=rerank_results)

        docs, applied, cache_hit = await perform_rerank(
            "query", documents, cache=None, reranker=reranker, top_k=1
        )

        assert len(docs) == 1
        assert applied is True
        assert cache_hit is False

    async def test_deprecated_colbert_reranker_is_ignored(self):
        """Deprecated client-side ColBERT service must not run in rerank core."""
        from telegram_bot.services.colbert_reranker import ColbertRerankerService

        documents = [{"text": "doc0", "score": 0.5}]
        client = MagicMock()
        client.rerank = AsyncMock(return_value=[{"index": 0, "score": 0.99}])

        with pytest.deprecated_call(match="deprecated"):
            reranker = ColbertRerankerService(client=client)

        docs, applied, cache_hit = await perform_rerank(
            "query", documents, cache=None, reranker=reranker, top_k=1
        )

        assert docs == documents
        assert applied is False
        assert cache_hit is False
        client.rerank.assert_not_awaited()


# ---------------------------------------------------------------------------
# H1: compute_query_embedding + check_semantic_cache
# ---------------------------------------------------------------------------


class TestComputeQueryEmbedding:
    """Tests for compute_query_embedding core function."""

    async def test_pre_computed_returns_immediately(self):
        """Pre-computed embedding bypasses cache and model calls."""
        cache = AsyncMock()
        embeddings = AsyncMock()
        pre_dense = [0.1] * 10
        pre_sparse = {"indices": [1], "values": [0.5]}
        pre_colbert = [[0.1] * 10]

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "query",
            cache=cache,
            embeddings=embeddings,
            pre_computed=pre_dense,
            pre_computed_sparse=pre_sparse,
            pre_computed_colbert=pre_colbert,
        )

        assert dense == pre_dense
        assert sparse == pre_sparse
        assert colbert == pre_colbert
        assert from_cache is False
        cache.get_embedding.assert_not_awaited()
        embeddings.aembed_query.assert_not_awaited()

    async def test_pre_computed_no_sparse_colbert_returns_none(self):
        """Pre-computed dense only: sparse and colbert are None."""
        cache = AsyncMock()
        embeddings = AsyncMock()
        pre_dense = [0.2] * 10

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "query",
            cache=cache,
            embeddings=embeddings,
            pre_computed=pre_dense,
        )

        assert dense == pre_dense
        assert sparse is None
        assert colbert is None
        assert from_cache is False

    async def test_from_redis_cache_returns_with_flag(self):
        """Embedding found in Redis: from_cache=True, no model call."""
        cached_dense = [0.2] * 10
        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=cached_dense)
        embeddings = AsyncMock()

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "query", cache=cache, embeddings=embeddings
        )

        assert dense == cached_dense
        assert sparse is None
        assert colbert is None
        assert from_cache is True
        embeddings.aembed_query.assert_not_awaited()

    async def test_hybrid_embedding_stores_both(self):
        """When aembed_hybrid is available, use it and store both vectors."""
        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()
        cache.store_sparse_embedding = AsyncMock()

        dense_vec = [0.3] * 10
        sparse_vec = {"indices": [2], "values": [0.8]}

        embeddings = AsyncMock()
        embeddings.aembed_hybrid = AsyncMock(return_value=(dense_vec, sparse_vec))

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "query", cache=cache, embeddings=embeddings
        )

        assert dense == dense_vec
        assert sparse == sparse_vec
        assert colbert is None
        assert from_cache is False
        cache.store_embedding.assert_awaited_once_with("query", dense_vec)
        cache.store_sparse_embedding.assert_awaited_once_with("query", sparse_vec)

    async def test_dense_only_embedding_stored(self):
        """When aembed_hybrid not available, use aembed_query."""
        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)
        cache.store_embedding = AsyncMock()

        dense_vec = [0.4] * 10

        # Use spec= so aembed_hybrid is absent → _has_hybrid = False
        embeddings = AsyncMock(spec=["aembed_query"])
        embeddings.aembed_query = AsyncMock(return_value=dense_vec)

        dense, sparse, colbert, from_cache = await compute_query_embedding(
            "query", cache=cache, embeddings=embeddings
        )

        assert dense == dense_vec
        assert sparse is None
        assert colbert is None
        assert from_cache is False
        cache.store_embedding.assert_awaited_once_with("query", dense_vec)

    async def test_embedding_error_raises_exception(self):
        """On embedding failure, raises the original exception."""
        cache = AsyncMock()
        cache.get_embedding = AsyncMock(return_value=None)

        embeddings = AsyncMock()
        embeddings.aembed_hybrid = AsyncMock(side_effect=RuntimeError("BGE-M3 connection failed"))

        with pytest.raises(RuntimeError, match="BGE-M3 connection failed"):
            await compute_query_embedding("query", cache=cache, embeddings=embeddings)


class TestCheckSemanticCache:
    """Tests for check_semantic_cache core function."""

    async def test_non_cacheable_type_returns_miss(self):
        """Non-cacheable query type skips cache.check_semantic entirely."""
        cache = AsyncMock()
        hit, response = await check_semantic_cache("query", [0.1] * 10, "APARTMENT", cache=cache)
        assert hit is False
        assert response is None
        cache.check_semantic.assert_not_awaited()

    async def test_cacheable_type_hit_returns_response(self):
        cache = AsyncMock()
        cache.check_semantic = AsyncMock(return_value="Cached FAQ answer")

        hit, response = await check_semantic_cache("query", [0.1] * 10, "FAQ", cache=cache)

        assert hit is True
        assert response == "Cached FAQ answer"

    async def test_cacheable_type_miss_returns_false(self):
        cache = AsyncMock()
        cache.check_semantic = AsyncMock(return_value=None)

        hit, response = await check_semantic_cache("query", [0.1] * 10, "GENERAL", cache=cache)

        assert hit is False
        assert response is None

    async def test_contextual_follow_up_skips_cache_lookup(self):
        cache = AsyncMock()
        cache.check_semantic = AsyncMock(return_value="cached answer")

        hit, response = await check_semantic_cache(
            "расскажи подробнее",
            [0.1] * 10,
            "FAQ",
            cache=cache,
        )

        assert hit is False
        assert response is None
        cache.check_semantic.assert_not_awaited()

    async def test_agent_role_passed_to_cache(self):
        """agent_role kwarg is forwarded to cache.check_semantic."""
        cache = AsyncMock()
        cache.check_semantic = AsyncMock(return_value="Role-gated response")

        hit, _response = await check_semantic_cache(
            "query", [0.1] * 10, "ENTITY", cache=cache, agent_role="sales"
        )

        assert hit is True
        call_kwargs = cache.check_semantic.call_args.kwargs
        assert call_kwargs.get("agent_role") == "sales"

    async def test_all_cacheable_types_are_checked(self):
        """CACHEABLE_QUERY_TYPES includes expected types."""
        assert "FAQ" in CACHEABLE_QUERY_TYPES
        assert "ENTITY" in CACHEABLE_QUERY_TYPES
        assert "STRUCTURED" in CACHEABLE_QUERY_TYPES
        assert "GENERAL" in CACHEABLE_QUERY_TYPES
        # Non-cacheable types not included
        assert "APARTMENT" not in CACHEABLE_QUERY_TYPES
