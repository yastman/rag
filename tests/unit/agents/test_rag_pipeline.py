"""Tests for rag_pipeline async functions (#442)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def mock_cache():
    cache = AsyncMock()
    cache.get_embedding = AsyncMock(return_value=None)
    cache.store_embedding = AsyncMock()
    cache.store_sparse_embedding = AsyncMock()
    cache.get_sparse_embedding = AsyncMock(return_value=None)
    cache.check_semantic = AsyncMock(return_value=None)
    cache.get_search_results = AsyncMock(return_value=None)
    cache.store_search_results = AsyncMock()
    cache.store_semantic = AsyncMock()
    return cache


@pytest.fixture
def mock_embeddings():
    emb = AsyncMock()
    emb.aembed_query = AsyncMock(return_value=[0.1] * 1024)
    emb.aembed_hybrid = AsyncMock(return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}))
    return emb


@pytest.fixture
def mock_sparse():
    sparse = AsyncMock()
    sparse.aembed_query = AsyncMock(return_value={"indices": [1], "values": [0.5]})
    return sparse


@pytest.fixture
def mock_qdrant():
    qdrant = AsyncMock()
    # Scores between relevance_threshold (0.005) and skip_rerank_threshold (0.012)
    # so rerank is always triggered in happy path
    qdrant.hybrid_search_rrf = AsyncMock(
        return_value=(
            [
                {"text": "Квартира 50м2", "score": 0.008, "metadata": {"title": "Doc1"}},
                {"text": "Апартаменты 80м2", "score": 0.006, "metadata": {"title": "Doc2"}},
            ],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )
    return qdrant


@pytest.fixture
def mock_reranker():
    reranker = AsyncMock()
    reranker.rerank = AsyncMock(
        return_value=[
            {"index": 0, "score": 0.95},
            {"index": 1, "score": 0.85},
        ]
    )
    return reranker


# ---------------------------------------------------------------------------
# _cache_check tests
# ---------------------------------------------------------------------------


async def test_cache_check_miss(mock_cache, mock_embeddings):
    from telegram_bot.agents.rag_pipeline import _cache_check

    result = await _cache_check(
        "квартиры в Несебре",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
    )

    assert result["cache_hit"] is False
    assert result["query_embedding"] is not None
    assert "cache_check" in result["latency_stages"]


async def test_cache_check_hit(mock_cache, mock_embeddings):
    from telegram_bot.agents.rag_pipeline import _cache_check

    mock_cache.get_embedding = AsyncMock(return_value=[0.1] * 1024)
    mock_cache.check_semantic = AsyncMock(return_value="Cached answer about apartments")

    result = await _cache_check(
        "квартиры",
        "FAQ",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
    )

    assert result["cache_hit"] is True
    assert result["cached_response"] == "Cached answer about apartments"


async def test_cache_check_embedding_error(mock_cache, mock_embeddings):
    from telegram_bot.agents.rag_pipeline import _cache_check

    mock_embeddings.aembed_hybrid = AsyncMock(side_effect=RuntimeError("BGE-M3 down"))

    result = await _cache_check(
        "test",
        "FAQ",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
    )

    assert result["cache_hit"] is False
    assert result["embedding_error"] is True
    assert result["query_embedding"] is None


async def test_cache_check_skips_semantic_for_general(mock_cache, mock_embeddings):
    """GENERAL query type bypasses semantic cache."""
    from telegram_bot.agents.rag_pipeline import _cache_check

    mock_cache.get_embedding = AsyncMock(return_value=[0.1] * 1024)

    result = await _cache_check(
        "расскажи про город",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
    )

    assert result["cache_hit"] is False
    mock_cache.check_semantic.assert_not_called()


# ---------------------------------------------------------------------------
# _hybrid_retrieve tests
# ---------------------------------------------------------------------------


async def test_hybrid_retrieve(mock_cache, mock_sparse, mock_qdrant):
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    result = await _hybrid_retrieve(
        "квартиры",
        [0.1] * 1024,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        latency_stages={},
    )

    assert len(result["documents"]) == 2
    assert result["search_results_count"] == 2
    assert "retrieve" in result["latency_stages"]


async def test_hybrid_retrieve_search_cache_hit(mock_cache, mock_sparse, mock_qdrant):
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    mock_cache.get_search_results = AsyncMock(
        return_value=[{"text": "cached doc", "score": 0.9, "metadata": {}}]
    )

    result = await _hybrid_retrieve(
        "test",
        [0.1] * 1024,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        latency_stages={},
    )

    assert result["search_cache_hit"] is True
    assert len(result["documents"]) == 1
    mock_qdrant.hybrid_search_rrf.assert_not_called()


# ---------------------------------------------------------------------------
# _grade_documents tests
# ---------------------------------------------------------------------------


async def test_grade_documents_relevant():
    from telegram_bot.agents.rag_pipeline import _grade_documents

    docs = [{"score": 0.015}, {"score": 0.010}]
    result = await _grade_documents(docs, 0.0, latency_stages={})

    assert result["documents_relevant"] is True
    assert result["grade_confidence"] == 0.015


async def test_grade_documents_empty():
    from telegram_bot.agents.rag_pipeline import _grade_documents

    result = await _grade_documents([], 0.0, latency_stages={})

    assert result["documents_relevant"] is False
    assert result["grade_confidence"] == 0.0


async def test_grade_documents_irrelevant():
    from telegram_bot.agents.rag_pipeline import _grade_documents

    docs = [{"score": 0.001}]
    result = await _grade_documents(docs, 0.0, latency_stages={})

    assert result["documents_relevant"] is False


# ---------------------------------------------------------------------------
# _rerank tests
# ---------------------------------------------------------------------------


async def test_rerank_with_colbert(mock_reranker):
    from telegram_bot.agents.rag_pipeline import _rerank

    docs = [
        {"text": "Doc A", "score": 0.5},
        {"text": "Doc B", "score": 0.3},
    ]

    result = await _rerank(
        "query",
        docs,
        reranker=mock_reranker,
        latency_stages={},
    )

    assert result["rerank_applied"] is True
    assert len(result["documents"]) == 2
    assert result["documents"][0]["score"] == 0.95


async def test_rerank_fallback_no_reranker():
    from telegram_bot.agents.rag_pipeline import _rerank

    docs = [{"text": "A", "score": 0.3}, {"text": "B", "score": 0.8}]

    result = await _rerank("query", docs, reranker=None, latency_stages={})

    assert result["rerank_applied"] is False
    assert result["documents"][0]["score"] == 0.8  # sorted desc


async def test_rerank_empty_docs():
    from telegram_bot.agents.rag_pipeline import _rerank

    result = await _rerank("query", [], reranker=None, latency_stages={})

    assert result["documents"] == []
    assert result["rerank_applied"] is False


# ---------------------------------------------------------------------------
# _rewrite_query tests
# ---------------------------------------------------------------------------


async def test_rewrite_query_success():
    from telegram_bot.agents.rag_pipeline import _rewrite_query

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "квартиры в Несебре до 50000 EUR"
    mock_response.model = "gpt-4o-mini"
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)

    result = await _rewrite_query(
        "квартиры",
        0,
        llm=mock_llm,
        latency_stages={},
    )

    assert result["rewrite_effective"] is True
    assert result["rewritten_query"] == "квартиры в Несебре до 50000 EUR"
    assert result["rewrite_count"] == 1


async def test_rewrite_query_llm_fails():
    from telegram_bot.agents.rag_pipeline import _rewrite_query

    mock_llm = MagicMock()
    mock_llm.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM down"))

    result = await _rewrite_query(
        "квартиры",
        0,
        llm=mock_llm,
        latency_stages={},
    )

    assert result["rewrite_effective"] is False
    assert result["rewritten_query"] == "квартиры"
    assert result["rewrite_count"] == 1


# ---------------------------------------------------------------------------
# _cache_store tests
# ---------------------------------------------------------------------------


async def test_cache_store_semantic(mock_cache):
    from telegram_bot.agents.rag_pipeline import _cache_store

    result = await _cache_store(
        "квартиры",
        "Ответ про квартиры",
        [0.1] * 1024,
        "FAQ",
        42,
        cache=mock_cache,
        latency_stages={},
    )

    assert result["stored_semantic"] is True
    mock_cache.store_semantic.assert_called_once()


async def test_cache_store_skips_non_cacheable(mock_cache):
    from telegram_bot.agents.rag_pipeline import _cache_store

    result = await _cache_store(
        "hi",
        "hello",
        [0.1] * 1024,
        "GENERAL",
        42,
        cache=mock_cache,
        latency_stages={},
    )

    assert result["stored_semantic"] is False
    mock_cache.store_semantic.assert_not_called()


# ---------------------------------------------------------------------------
# rag_pipeline (full flow) tests
# ---------------------------------------------------------------------------


async def test_pipeline_cache_hit(mock_cache, mock_embeddings, mock_sparse, mock_qdrant):
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    mock_cache.get_embedding = AsyncMock(return_value=[0.1] * 1024)
    mock_cache.check_semantic = AsyncMock(return_value="Cached answer")

    result = await rag_pipeline(
        "квартиры",
        user_id=42,
        session_id="test",
        query_type="FAQ",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
    )

    assert result["cache_hit"] is True
    assert result["response"] == "Cached answer"
    mock_qdrant.hybrid_search_rrf.assert_not_called()


async def test_pipeline_happy_path(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant, mock_reranker
):
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    result = await rag_pipeline(
        "квартиры в Несебре",
        user_id=42,
        session_id="test",
        query_type="GENERAL",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        reranker=mock_reranker,
    )

    assert result["cache_hit"] is False
    assert len(result["documents"]) > 0
    assert "latency_stages" in result
    assert result["rerank_applied"] is True


async def test_pipeline_rewrite_loop(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant, mock_reranker
):
    """Pipeline retries with rewrite when documents are irrelevant."""
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    # First retrieve returns low scores, second returns high scores
    call_count = 0
    low_results = (
        [{"text": "irrelevant", "score": 0.001, "metadata": {}}],
        {"backend_error": False, "error_type": None, "error_message": None},
    )
    high_results = (
        [
            {"text": "Квартира 50м2", "score": 0.008, "metadata": {"title": "Doc1"}},
            {"text": "Апартаменты 80м2", "score": 0.006, "metadata": {"title": "Doc2"}},
        ],
        {"backend_error": False, "error_type": None, "error_message": None},
    )

    async def side_effect(**kwargs):
        nonlocal call_count
        call_count += 1
        return low_results if call_count == 1 else high_results

    mock_qdrant.hybrid_search_rrf = AsyncMock(side_effect=side_effect)

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "улучшенный запрос"
    mock_response.model = "gpt-4o-mini"
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch.dict("os.environ", {"MAX_REWRITE_ATTEMPTS": "1"}):
        result = await rag_pipeline(
            "непонятный запрос",
            user_id=42,
            session_id="test",
            cache=mock_cache,
            embeddings=mock_embeddings,
            sparse_embeddings=mock_sparse,
            qdrant=mock_qdrant,
            reranker=mock_reranker,
            llm=mock_llm,
        )

    assert result["rewrite_count"] >= 1
    assert len(result["documents"]) > 0


# ---------------------------------------------------------------------------
# original_query cache key tests (#430)
# ---------------------------------------------------------------------------


async def test_pipeline_cache_hit_via_original_query(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant
):
    """Cache hit when original_query matches stored key, even with different reformulated query.

    Scenario: user sends "квартиры в Несебре до 80000", agent reformulates to
    "apartments in Nesebar under 80000 EUR". The cache was keyed on the original
    Russian text. After the fix, the pipeline checks the cache with original_query
    and returns the cached response without going to retrieval.
    """
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    # Cache has an entry stored under the original query
    mock_cache.get_embedding = AsyncMock(return_value=[0.1] * 1024)
    mock_cache.check_semantic = AsyncMock(return_value="Cached answer about Nesebar apartments")

    result = await rag_pipeline(
        "apartments in Nesebar under 80000 EUR",  # agent-reformulated query
        original_query="квартиры в Несебре до 80000",  # original user query
        user_id=42,
        session_id="test",
        query_type="FAQ",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
    )

    assert result["cache_hit"] is True
    assert result["response"] == "Cached answer about Nesebar apartments"
    # Retrieval must NOT be called when cache hits
    mock_qdrant.hybrid_search_rrf.assert_not_called()
    # Cache was checked with the ORIGINAL query (not the reformulated one)
    check_call = mock_cache.check_semantic.call_args
    assert check_call.kwargs["query"] == "квартиры в Несебре до 80000"


async def test_pipeline_cache_uses_original_query_as_key(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant
):
    """_cache_check is invoked with original_query as the cache key.

    When original_query is provided, the semantic cache lookup must use it
    (not the reformulated query) so the hit rate is consistent regardless of
    how the agent chose to reformulate the user's question.
    """
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    # Cache miss — proceed to retrieval
    mock_cache.get_embedding = AsyncMock(return_value=None)
    mock_cache.check_semantic = AsyncMock(return_value=None)

    await rag_pipeline(
        "apartments in Nesebar",  # reformulated
        original_query="квартиры в Несебре",  # original
        user_id=42,
        session_id="test",
        query_type="FAQ",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
    )

    # Embedding was computed for the ORIGINAL query
    embed_call_args = [str(c) for c in mock_embeddings.aembed_hybrid.call_args_list]
    assert any("квартиры в Несебре" in a for a in embed_call_args)
    # Semantic check was done with the original query key
    check_call = mock_cache.check_semantic.call_args
    assert check_call.kwargs["query"] == "квартиры в Несебре"


async def test_pipeline_fallback_to_query_when_original_query_empty(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant
):
    """When original_query is empty (voice path / direct call), cache key falls back to query."""
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    mock_cache.get_embedding = AsyncMock(return_value=None)
    mock_cache.check_semantic = AsyncMock(return_value=None)

    await rag_pipeline(
        "квартиры в Несебре",
        original_query="",  # empty — backward compat mode
        user_id=42,
        session_id="test",
        query_type="FAQ",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
    )

    # Fallback: cache was checked with the query itself
    check_call = mock_cache.check_semantic.call_args
    assert check_call.kwargs["query"] == "квартиры в Несебре"


async def test_pipeline_cache_miss_when_different_original_query(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant
):
    """Cache miss when a different original_query doesn't match the stored key."""
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    # Cache returns None (miss) regardless of which key we check
    mock_cache.get_embedding = AsyncMock(return_value=None)
    mock_cache.check_semantic = AsyncMock(return_value=None)

    result = await rag_pipeline(
        "apartments in Varna",
        original_query="квартиры в Варне",  # different from any stored key
        user_id=42,
        session_id="test",
        query_type="FAQ",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
    )

    assert result["cache_hit"] is False
    # Retrieval was executed after the miss
    mock_qdrant.hybrid_search_rrf.assert_called_once()


async def test_pipeline_embedding_error(mock_cache, mock_sparse, mock_qdrant):
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    bad_embeddings = AsyncMock()
    bad_embeddings.aembed_hybrid = AsyncMock(side_effect=RuntimeError("BGE-M3 down"))

    result = await rag_pipeline(
        "test",
        user_id=42,
        session_id="test",
        cache=mock_cache,
        embeddings=bad_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
    )

    assert result["embedding_error"] is True
    assert result["cache_hit"] is False
    assert result["documents"] == []
