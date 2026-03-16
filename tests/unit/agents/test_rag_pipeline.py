"""Tests for rag_pipeline async functions (#442)."""

from __future__ import annotations

import logging
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
    cache.get_rerank_results = AsyncMock(return_value=None)
    cache.store_rerank_results = AsyncMock()
    cache.store_semantic = AsyncMock()
    return cache


@pytest.fixture
def mock_embeddings():
    emb = AsyncMock()
    emb.aembed_query = AsyncMock(return_value=[0.1] * 1024)
    emb.aembed_hybrid = AsyncMock(return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}))
    emb.aembed_hybrid_with_colbert = None  # not available; prevents auto-AsyncMock child
    emb.aembed_colbert_query = None
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
    mock_embeddings.aembed_colbert_query = AsyncMock(return_value=[[0.2] * 1024])

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
    mock_embeddings.aembed_colbert_query.assert_not_awaited()


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


async def test_cache_check_uses_semantic_for_general(mock_cache, mock_embeddings):
    """GENERAL query type participates in semantic cache lookup."""
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
    mock_cache.check_semantic.assert_awaited_once()
    call_kwargs = mock_cache.check_semantic.call_args.kwargs
    assert call_kwargs["query_type"] == "GENERAL"
    assert "user_id" not in call_kwargs
    assert call_kwargs.get("cache_scope") == "rag"


async def test_cache_check_passes_rag_scope(mock_cache, mock_embeddings):
    """_cache_check passes cache_scope='rag' to check_semantic."""
    from telegram_bot.agents.rag_pipeline import _cache_check

    mock_cache.get_embedding = AsyncMock(return_value=[0.1] * 1024)
    mock_cache.check_semantic = AsyncMock(return_value=None)

    await _cache_check(
        "query",
        "FAQ",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
    )

    call_kwargs = mock_cache.check_semantic.call_args.kwargs
    assert call_kwargs.get("cache_scope") == "rag"


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


async def test_hybrid_retrieve_passes_topic_filter(mock_cache, mock_sparse, mock_qdrant):
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    await _hybrid_retrieve(
        "какие есть варианты рассрочки",
        [0.1] * 1024,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        topic_hint="finance",
        latency_stages={},
    )

    first_call = mock_qdrant.hybrid_search_rrf.await_args_list[0].kwargs
    assert first_call["filters"] == {"topic": "finance"}


async def test_hybrid_retrieve_prefers_faq_candidates_for_short_finance_query(
    mock_cache, mock_sparse
):
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    mock_qdrant = AsyncMock()
    mock_qdrant.hybrid_search_rrf = AsyncMock(
        return_value=(
            [{"text": "FAQ рассрочка", "score": 0.9, "metadata": {"doc_type": "faq"}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    result = await _hybrid_retrieve(
        "рассрочки",
        [0.1] * 1024,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        topic_hint="finance",
        latency_stages={},
    )

    assert result["search_results_count"] > 0
    first_call = mock_qdrant.hybrid_search_rrf.await_args_list[0].kwargs
    assert first_call["filters"] == {"topic": "finance", "doc_type": "faq"}


async def test_hybrid_retrieve_omits_topic_filter_by_default(mock_cache, mock_sparse, mock_qdrant):
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    await _hybrid_retrieve(
        "квартиры",
        [0.1] * 1024,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        latency_stages={},
    )

    assert mock_qdrant.hybrid_search_rrf.call_args.kwargs["filters"] is None


async def test_hybrid_retrieve_retries_without_topic_filter_when_results_too_small(
    mock_cache, mock_sparse
):
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    mock_qdrant = AsyncMock()
    mock_qdrant.hybrid_search_rrf = AsyncMock(
        side_effect=[
            ([{"text": "narrow", "score": 0.9, "metadata": {}}], {"backend_error": False}),
            (
                [
                    {"text": "broad-1", "score": 0.9, "metadata": {}},
                    {"text": "broad-2", "score": 0.8, "metadata": {}},
                    {"text": "broad-3", "score": 0.7, "metadata": {}},
                ],
                {"backend_error": False},
            ),
        ]
    )

    result = await _hybrid_retrieve(
        "какие есть варианты рассрочки",
        [0.1] * 1024,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        topic_hint="finance",
        latency_stages={},
    )

    assert len(result["documents"]) == 3
    assert mock_qdrant.hybrid_search_rrf.await_count == 2
    first_call = mock_qdrant.hybrid_search_rrf.await_args_list[0].kwargs
    second_call = mock_qdrant.hybrid_search_rrf.await_args_list[1].kwargs
    assert first_call["filters"] == {"topic": "finance"}
    assert second_call["filters"] is None


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


async def test_grade_documents_includes_score_gap_confident():
    from telegram_bot.agents.rag_pipeline import _grade_documents

    docs = [{"score": 0.0164}, {"score": 0.0160}, {"score": 0.0158}]
    result = await _grade_documents(docs, 0.0, latency_stages={})

    assert result["score_gap_confident"] is False


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
        cache=AsyncMock(get_rerank_results=AsyncMock(return_value=None)),
        reranker=mock_reranker,
        latency_stages={},
    )

    assert result["rerank_applied"] is True
    assert result["rerank_cache_hit"] is False
    assert len(result["documents"]) == 2
    assert result["documents"][0]["score"] == 0.95


async def test_rerank_fallback_no_reranker():
    from telegram_bot.agents.rag_pipeline import _rerank

    docs = [{"text": "A", "score": 0.3}, {"text": "B", "score": 0.8}]

    result = await _rerank("query", docs, reranker=None, latency_stages={})

    assert result["rerank_applied"] is False
    assert result["rerank_cache_hit"] is False
    assert result["documents"][0]["score"] == 0.8  # sorted desc


async def test_rerank_empty_docs():
    from telegram_bot.agents.rag_pipeline import _rerank

    result = await _rerank("query", [], reranker=None, latency_stages={})

    assert result["documents"] == []
    assert result["rerank_applied"] is False
    assert result["rerank_cache_hit"] is False


async def test_rerank_uses_cache_hit(mock_reranker):
    from telegram_bot.agents.rag_pipeline import _rerank

    docs = [{"text": "A", "score": 0.1}, {"text": "B", "score": 0.2}]
    cached = [{"text": "B", "score": 0.9}]
    cache = AsyncMock()
    cache.get_rerank_results = AsyncMock(return_value=cached)
    cache.store_rerank_results = AsyncMock()

    result = await _rerank("query", docs, cache=cache, reranker=mock_reranker, latency_stages={})

    assert result["rerank_applied"] is True
    assert result["rerank_cache_hit"] is True
    assert result["documents"] == cached
    mock_reranker.rerank.assert_not_awaited()


async def test_grade_or_rerank_drops_weak_tail_when_gap_is_small():
    from telegram_bot.agents.rag_pipeline import _rerank

    docs = [
        {"score": 1.0, "text": "finance faq"},
        {"score": 0.95, "text": "finance note"},
        {"score": 0.52, "text": "ВНЖ"},
    ]
    result = await _rerank("рассрочки", docs, reranker=None, latency_stages={})

    assert len(result["documents"]) == 2
    assert all("ВНЖ" not in d["text"] for d in result["documents"])


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


async def test_short_finance_query_expands_before_rewrite_loop():
    from telegram_bot.agents.rag_pipeline import _rewrite_query

    fake_llm = MagicMock()
    fake_llm.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM should not be used"))

    result = await _rewrite_query(
        "рассрочки",
        0,
        llm=fake_llm,
        latency_stages={},
    )

    assert result["rewritten_query"] != "рассрочки"


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
    call_kwargs = mock_cache.store_semantic.call_args[1]
    assert call_kwargs.get("cache_scope") == "rag"


async def test_cache_store_skips_non_cacheable(mock_cache):
    from telegram_bot.agents.rag_pipeline import _cache_store

    result = await _cache_store(
        "hi",
        "hello",
        [0.1] * 1024,
        "CHITCHAT",
        42,
        cache=mock_cache,
        latency_stages={},
    )

    assert result["stored_semantic"] is False
    mock_cache.store_semantic.assert_not_called()


async def test_cache_store_exception_preserves_response_and_logs_warning(mock_cache, caplog):
    """store_semantic raises Exception → response not lost, warning is logged (#524)."""
    import logging

    from telegram_bot.agents.rag_pipeline import _cache_store

    mock_cache.store_semantic = AsyncMock(side_effect=Exception("Redis gone"))

    with caplog.at_level(logging.WARNING, logger="telegram_bot.agents.rag_pipeline"):
        result = await _cache_store(
            "квартира у моря",
            "Ответ про квартиры",
            [0.1] * 1024,
            "FAQ",
            42,
            cache=mock_cache,
            latency_stages={},
        )

    # Response is preserved — not lost on cache error
    assert result["stored_semantic"] is False
    # Latency stage is still populated
    assert "cache_store" in result["latency_stages"]
    # Warning was emitted
    assert any(
        "cache_store" in r.message or "semantic store failed" in r.message for r in caplog.records
    )


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


async def test_pipeline_reformulation_skips_embed_on_warm_cache(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant
):
    """Reformulated query embedding in cache prevents a redundant BGE-M3 call (#513).

    Scenario: embeddings_cache_hit=True for original query, but the agent reformulated.
    On the second+ request the reformulated embedding is also cached — aembed_hybrid
    must NOT be called (no 'bge-m3-hybrid-embed' span).
    """
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    original_emb = [0.1] * 1024
    reform_emb = [0.2] * 1024  # distinct embedding for reformulated query

    def _get_embedding(text: str):
        if "квартиры" in text:
            return original_emb  # original query — warm
        if "apartments" in text:
            return reform_emb  # reformulated query — warm
        return None

    mock_cache.get_embedding = AsyncMock(side_effect=_get_embedding)
    mock_cache.check_semantic = AsyncMock(return_value=None)  # semantic miss → full retrieval
    mock_cache.get_sparse_embedding = AsyncMock(return_value={"indices": [1], "values": [0.5]})

    result = await rag_pipeline(
        "apartments in Nesebar",  # agent-reformulated query
        original_query="квартиры в Несебре",  # original user query
        user_id=42,
        session_id="test",
        query_type="GENERAL",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
    )

    # Reformulated embedding was in cache — BGE-M3 must NOT be called
    mock_embeddings.aembed_hybrid.assert_not_called()
    mock_embeddings.aembed_query.assert_not_called()
    assert result["cache_hit"] is False
    mock_qdrant.hybrid_search_rrf.assert_called_once()
    # Verify the orchestrator pre-fetched the reformulated query embedding from
    # cache (the mechanism of the fix — not just the observable BGE-M3 side-effect).
    get_embedding_calls = [str(c.args[0]) for c in mock_cache.get_embedding.call_args_list]
    assert any("apartments" in c for c in get_embedding_calls)


async def test_pipeline_embedding_error(mock_cache, mock_sparse, mock_qdrant):
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    bad_embeddings = AsyncMock()
    bad_embeddings.aembed_hybrid = AsyncMock(side_effect=RuntimeError("BGE-M3 down"))
    bad_embeddings.aembed_hybrid_with_colbert = None  # not available

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


# ---------------------------------------------------------------------------
# skip_rewrite tests
# ---------------------------------------------------------------------------


async def test_skip_rewrite_bypasses_rewrite_loop(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant, mock_reranker
):
    """skip_rewrite=True prevents _rewrite_query from being called."""
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    # Return irrelevant docs so the rewrite check is reached
    mock_qdrant.hybrid_search_rrf = AsyncMock(
        return_value=(
            [{"text": "irrelevant", "score": 0.001, "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    with (
        patch(
            "telegram_bot.agents.rag_pipeline._rewrite_query",
            new_callable=AsyncMock,
        ) as mock_rewrite,
        patch.dict("os.environ", {"MAX_REWRITE_ATTEMPTS": "1"}),
    ):
        result = await rag_pipeline(
            "вопрос",
            user_id=42,
            session_id="test",
            cache=mock_cache,
            embeddings=mock_embeddings,
            sparse_embeddings=mock_sparse,
            qdrant=mock_qdrant,
            reranker=mock_reranker,
            skip_rewrite=True,
        )

    mock_rewrite.assert_not_called()
    assert result["skip_rewrite"] is True


async def test_skip_rewrite_false_allows_rewrite(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant, mock_reranker
):
    """skip_rewrite=False (default) allows the rewrite loop to execute."""
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    # Return irrelevant docs so rewrite condition is reached
    mock_qdrant.hybrid_search_rrf = AsyncMock(
        return_value=(
            [{"text": "irrelevant", "score": 0.001, "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    mock_rewrite_result = {
        "rewrite_effective": True,
        "rewritten_query": "улучшенный запрос",
        "rewrite_count": 1,
        "latency_stages": {},
    }

    with (
        patch(
            "telegram_bot.agents.rag_pipeline._rewrite_query",
            new=AsyncMock(return_value=mock_rewrite_result),
        ) as mock_rewrite,
        patch.dict("os.environ", {"MAX_REWRITE_ATTEMPTS": "1"}),
    ):
        result = await rag_pipeline(
            "вопрос",
            user_id=42,
            session_id="test",
            cache=mock_cache,
            embeddings=mock_embeddings,
            sparse_embeddings=mock_sparse,
            qdrant=mock_qdrant,
            reranker=mock_reranker,
            skip_rewrite=False,
        )

    mock_rewrite.assert_called_once()
    assert result["skip_rewrite"] is False


async def test_skip_rewrite_in_result(
    mock_cache, mock_embeddings, mock_sparse, mock_qdrant, mock_reranker
):
    """result dict contains 'skip_rewrite' key reflecting the passed value."""
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    result_true = await rag_pipeline(
        "квартиры",
        user_id=42,
        session_id="test",
        query_type="GENERAL",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        reranker=mock_reranker,
        skip_rewrite=True,
    )
    assert "skip_rewrite" in result_true
    assert result_true["skip_rewrite"] is True

    result_false = await rag_pipeline(
        "квартиры",
        user_id=42,
        session_id="test",
        query_type="GENERAL",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        reranker=mock_reranker,
        skip_rewrite=False,
    )
    assert "skip_rewrite" in result_false
    assert result_false["skip_rewrite"] is False


# ---------------------------------------------------------------------------
# ColBERT wiring tests (Tasks 8 & 10, #568)
# ---------------------------------------------------------------------------


async def test_cache_check_returns_colbert_query(mock_cache):
    """_cache_check returns colbert_query when embeddings has aembed_hybrid_with_colbert."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import _cache_check

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid = None
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=(
            [0.1] * 1024,
            {"indices": [1], "values": [0.5]},
            [[0.2] * 1024] * 4,
        )
    )
    mock_embeddings.aembed_colbert_query = None

    result = await _cache_check(
        "test query",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
    )

    assert result["cache_hit"] is False
    assert result["colbert_query"] is not None
    assert len(result["colbert_query"]) == 4
    assert len(result["colbert_query"][0]) == 1024
    mock_embeddings.aembed_hybrid_with_colbert.assert_awaited_once()


async def test_cache_check_colbert_query_none_without_hybrid_colbert(mock_cache, mock_embeddings):
    """_cache_check returns colbert_query=None when only aembed_hybrid is available."""
    from telegram_bot.agents.rag_pipeline import _cache_check

    result = await _cache_check(
        "test query",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
    )

    assert result["colbert_query"] is None


async def test_cache_check_computes_colbert_when_embedding_cached(mock_cache):
    """_cache_check computes ColBERT vectors even when dense embedding is cached."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import _cache_check

    mock_cache.get_embedding = AsyncMock(return_value=[0.1] * 1024)  # cached!

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid = None
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=(
            [0.1] * 1024,
            {"indices": [1], "values": [0.5]},
            [[0.2] * 1024] * 4,
        )
    )
    mock_embeddings.aembed_colbert_query = None

    result = await _cache_check(
        "test query",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
    )

    assert result["colbert_query"] is not None
    assert len(result["colbert_query"]) == 4
    mock_embeddings.aembed_hybrid_with_colbert.assert_awaited_once()


async def test_hybrid_retrieve_recomputes_colbert_after_rewrite(mock_cache, mock_sparse):
    """_hybrid_retrieve re-embeds with ColBERT when dense_vector is None (post-rewrite)."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    mock_qdrant = AsyncMock()
    mock_qdrant.hybrid_search_rrf_colbert = AsyncMock(
        return_value=(
            [{"id": "1", "score": 85.0, "text": "doc", "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=(
            [0.3] * 1024,
            {"indices": [2], "values": [0.7]},
            [[0.4] * 1024] * 3,
        )
    )

    # query_embedding=None simulates post-rewrite state
    result = await _hybrid_retrieve(
        "rewritten query",
        None,  # dense_vector is None after rewrite
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        embeddings=mock_embeddings,
        colbert_query=None,  # was reset after rewrite
        latency_stages={},
    )

    assert result["rerank_applied"] is True
    assert result["colbert_query"] is not None
    assert len(result["colbert_query"]) == 3
    mock_embeddings.aembed_hybrid_with_colbert.assert_awaited_once()
    mock_qdrant.hybrid_search_rrf_colbert.assert_called_once()


async def test_hybrid_retrieve_uses_colbert_search(mock_cache, mock_sparse):
    """_hybrid_retrieve calls hybrid_search_rrf_colbert when colbert_query is provided."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    mock_qdrant = AsyncMock()
    mock_qdrant.hybrid_search_rrf_colbert = AsyncMock(
        return_value=(
            [{"id": "1", "score": 85.0, "text": "doc", "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )
    mock_qdrant.hybrid_search_rrf = AsyncMock()

    colbert_query = [[0.2] * 1024] * 4

    result = await _hybrid_retrieve(
        "test",
        [0.1] * 1024,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        colbert_query=colbert_query,
        latency_stages={},
    )

    assert len(result["documents"]) == 1
    assert result["rerank_applied"] is True
    mock_qdrant.hybrid_search_rrf_colbert.assert_called_once()
    mock_qdrant.hybrid_search_rrf.assert_not_called()


async def test_hybrid_retrieve_fallback_without_colbert_query(mock_cache, mock_sparse, mock_qdrant):
    """_hybrid_retrieve falls back to hybrid_search_rrf when colbert_query is None."""
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    result = await _hybrid_retrieve(
        "test",
        [0.1] * 1024,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        colbert_query=None,
        latency_stages={},
    )

    assert len(result["documents"]) == 2
    assert result["rerank_applied"] is False
    mock_qdrant.hybrid_search_rrf.assert_called_once()


async def test_rag_pipeline_uses_colbert_search(mock_cache, mock_sparse):
    """rag_pipeline uses hybrid_search_rrf_colbert when embeddings supports it."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import rag_pipeline

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=(
            [0.1] * 1024,
            {"indices": [1], "values": [0.5]},
            [[0.2] * 1024] * 4,
        )
    )
    mock_embeddings.aembed_hybrid = AsyncMock(
        return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]})
    )
    mock_embeddings.aembed_colbert_query = AsyncMock(return_value=[[0.2] * 1024] * 4)

    mock_qdrant = AsyncMock()
    mock_qdrant.hybrid_search_rrf_colbert = AsyncMock(
        return_value=(
            [{"id": "1", "score": 85.0, "text": "doc", "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    result = await rag_pipeline(
        "test query",
        user_id=1,
        session_id="s1",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        reranker=None,
    )

    mock_qdrant.hybrid_search_rrf_colbert.assert_called_once()
    assert result["documents"]


async def test_rag_pipeline_skips_rerank_when_colbert_used(mock_cache, mock_sparse):
    """When hybrid_search_rrf_colbert is used, _rerank is NOT called."""
    from unittest.mock import AsyncMock, patch

    from telegram_bot.agents.rag_pipeline import rag_pipeline

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=(
            [0.1] * 1024,
            {"indices": [1], "values": [0.5]},
            [[0.2] * 1024] * 4,
        )
    )
    mock_embeddings.aembed_hybrid = AsyncMock(
        return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]})
    )
    mock_embeddings.aembed_colbert_query = AsyncMock(return_value=[[0.2] * 1024] * 4)

    mock_qdrant = AsyncMock()
    # Score between relevance_threshold (0.005) and skip_rerank_threshold (0.018)
    # so grade says skip_rerank=False, but ColBERT path sets rerank_applied=True
    mock_qdrant.hybrid_search_rrf_colbert = AsyncMock(
        return_value=(
            [{"id": "1", "score": 0.008, "text": "doc", "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    mock_reranker = AsyncMock()
    mock_reranker.rerank = AsyncMock(return_value=[{"index": 0, "score": 0.9}])

    with patch(
        "telegram_bot.agents.rag_pipeline._rerank",
        new_callable=AsyncMock,
    ) as mock_rerank_fn:
        result = await rag_pipeline(
            "test query",
            user_id=1,
            session_id="s1",
            cache=mock_cache,
            embeddings=mock_embeddings,
            sparse_embeddings=mock_sparse,
            qdrant=mock_qdrant,
            reranker=mock_reranker,
        )

    mock_rerank_fn.assert_not_called()
    assert result["rerank_applied"] is True


async def test_rag_pipeline_recomputes_colbert_for_reformulated_query(mock_cache, mock_sparse):
    """#951: When original_query != query, don't call aembed_colbert_query separately.
    Instead set query_embedding=None and let _hybrid_retrieve do one combined call."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import rag_pipeline

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid = AsyncMock(
        return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]})
    )
    mock_embeddings.aembed_hybrid_with_colbert = None
    mock_embeddings.aembed_colbert_query = AsyncMock(return_value=[[0.7] * 1024])

    mock_qdrant = AsyncMock()
    mock_qdrant.hybrid_search_rrf = AsyncMock(
        return_value=(
            [{"id": "1", "score": 0.008, "text": "doc", "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    await rag_pipeline(
        "reformulated query",
        user_id=1,
        session_id="s1",
        query_type="GENERAL",
        original_query="original user query",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        reranker=None,
    )

    # #951 fix: aembed_colbert_query called once for cache_key in _cache_check,
    # but NOT a second time for the reformulated query (old behavior was 2 calls).
    assert mock_embeddings.aembed_colbert_query.call_count <= 1


# ---------------------------------------------------------------------------
# Pre-computed sparse + colbert passthrough (#571)
# ---------------------------------------------------------------------------


async def test_cache_check_uses_pre_computed_sparse(mock_cache):
    """_cache_check reuses pre_computed_sparse without re-storing (pre-agent already stored)."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import _cache_check

    dense = [0.1] * 1024
    sparse = {"indices": [1, 2], "values": [0.5, 0.3]}

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = None  # not available
    mock_embeddings.aembed_colbert_query = None

    result = await _cache_check(
        "test query",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
        pre_computed_embedding=dense,
        pre_computed_sparse=sparse,
    )

    assert result["sparse_embedding"] == sparse
    # Pre-agent already stored embeddings — _cache_check must NOT re-store (#633)
    mock_cache.store_sparse_embedding.assert_not_awaited()
    mock_cache.store_embedding.assert_not_awaited()
    assert result["cache_hit"] is False
    assert result["query_embedding"] == dense


async def test_cache_check_uses_pre_computed_colbert_skips_reencode(mock_cache):
    """_cache_check uses pre_computed_colbert and does NOT call aembed_hybrid_with_colbert."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import _cache_check

    dense = [0.1] * 1024
    colbert = [[0.2] * 1024] * 3

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid = None
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=(dense, {"indices": [1], "values": [0.5]}, colbert)
    )
    mock_embeddings.aembed_colbert_query = None

    result = await _cache_check(
        "test query",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
        pre_computed_embedding=dense,
        pre_computed_colbert=colbert,
    )

    assert result["colbert_query"] == colbert
    # Must NOT call aembed_hybrid_with_colbert since colbert was pre-computed
    mock_embeddings.aembed_hybrid_with_colbert.assert_not_awaited()


async def test_cache_check_no_redundant_stores_or_embeds_with_all_precomputed(mock_cache):
    """_cache_check with all three pre-computed skips stores AND extra BGE-M3 calls (#633)."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import _cache_check

    dense = [0.1] * 1024
    sparse = {"indices": [1, 2], "values": [0.5, 0.3]}
    colbert = [[0.2] * 1024] * 3

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock()
    mock_embeddings.aembed_colbert_query = AsyncMock()

    result = await _cache_check(
        "test query",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
        pre_computed_embedding=dense,
        pre_computed_sparse=sparse,
        pre_computed_colbert=colbert,
    )

    # No redundant cache stores — pre-agent already stored (#633)
    mock_cache.store_embedding.assert_not_awaited()
    mock_cache.store_sparse_embedding.assert_not_awaited()
    # No redundant BGE-M3 calls — all vectors pre-computed
    mock_embeddings.aembed_hybrid.assert_not_awaited()
    mock_embeddings.aembed_hybrid_with_colbert.assert_not_awaited()
    mock_embeddings.aembed_colbert_query.assert_not_awaited()
    # All vectors passed through
    assert result["query_embedding"] == dense
    assert result["sparse_embedding"] == sparse
    assert result["colbert_query"] == colbert
    assert result["cache_hit"] is False


async def test_cache_check_stores_sparse_when_not_pre_computed(mock_cache):
    """When pre_computed_sparse is None, store_sparse_embedding IS called after hybrid_with_colbert."""
    from telegram_bot.agents.rag_pipeline import _cache_check

    dense = [0.1] * 1024
    sparse_from_hybrid = {"indices": [2], "values": [0.9]}
    colbert_from_hybrid = [[0.2] * 1024]

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=(dense, sparse_from_hybrid, colbert_from_hybrid)
    )
    mock_embeddings.aembed_colbert_query = None

    result = await _cache_check(
        "test query",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
        pre_computed_embedding=dense,
        pre_computed_sparse=None,
    )

    assert result["cache_hit"] is False
    mock_cache.store_sparse_embedding.assert_awaited_once_with("test query", sparse_from_hybrid)


async def test_cache_check_skips_sparse_store_when_pre_computed(mock_cache):
    """When pre_computed_sparse is truthy, store_sparse_embedding is NOT called."""
    from telegram_bot.agents.rag_pipeline import _cache_check

    dense = [0.1] * 1024
    existing_sparse = {"indices": [1], "values": [0.5]}
    sparse_from_hybrid = {"indices": [2], "values": [0.9]}
    colbert_from_hybrid = [[0.2] * 1024]

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = AsyncMock(
        return_value=(dense, sparse_from_hybrid, colbert_from_hybrid)
    )
    mock_embeddings.aembed_colbert_query = None

    result = await _cache_check(
        "test query",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
        pre_computed_embedding=dense,
        pre_computed_sparse=existing_sparse,
    )

    assert result["cache_hit"] is False
    mock_cache.store_sparse_embedding.assert_not_awaited()


async def test_cache_check_returns_sparse_embedding_in_all_paths(mock_cache):
    """_cache_check returns sparse_embedding key in result for both HIT and MISS."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import _cache_check

    dense = [0.1] * 1024
    sparse = {"indices": [1], "values": [0.5]}

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = None
    mock_embeddings.aembed_colbert_query = None

    # MISS path
    result_miss = await _cache_check(
        "miss query",
        "GENERAL",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
        pre_computed_embedding=dense,
        pre_computed_sparse=sparse,
    )
    assert "sparse_embedding" in result_miss

    # HIT path
    mock_cache.check_semantic = AsyncMock(return_value="cached answer")
    result_hit = await _cache_check(
        "hit query",
        "FAQ",
        42,
        cache=mock_cache,
        embeddings=mock_embeddings,
        latency_stages={},
        pre_computed_embedding=dense,
        pre_computed_sparse=sparse,
    )
    assert "sparse_embedding" in result_hit
    assert result_hit["sparse_embedding"] == sparse


async def test_hybrid_retrieve_uses_pre_computed_sparse(mock_cache, mock_sparse, mock_qdrant):
    """_hybrid_retrieve uses sparse_embedding param and skips cache fetch + recompute."""
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    pre_sparse = {"indices": [5], "values": [0.9]}
    dense = [0.1] * 1024

    result = await _hybrid_retrieve(
        "test query",
        dense,
        cache=mock_cache,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        sparse_embedding=pre_sparse,
        latency_stages={},
    )

    # Sparse cache and recompute must NOT be called — pre-computed sparse was provided
    mock_cache.get_sparse_embedding.assert_not_awaited()
    mock_sparse.aembed_query.assert_not_awaited()
    assert result["documents"]


async def test_hybrid_retrieve_logs_colbert_rerank_attempted(mock_cache, mock_sparse, caplog):
    """_hybrid_retrieve logs colbert_rerank_attempted metric when ColBERT path is taken."""
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    mock_qdrant = AsyncMock()
    mock_qdrant.hybrid_search_rrf_colbert = AsyncMock(
        return_value=(
            [{"id": "1", "score": 85.0, "text": "doc", "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    with caplog.at_level(logging.INFO):
        await _hybrid_retrieve(
            "test",
            [0.1] * 1024,
            cache=mock_cache,
            sparse_embeddings=mock_sparse,
            qdrant=mock_qdrant,
            colbert_query=[[0.2] * 1024] * 4,
            latency_stages={},
        )

    metric_records = [r for r in caplog.records if r.getMessage() == "metric"]
    names = [getattr(r, "metric_name", None) for r in metric_records]
    assert "colbert_rerank_attempted" in names


async def test_hybrid_retrieve_logs_retrieval_zero_docs(mock_cache, mock_sparse, caplog):
    """_hybrid_retrieve logs retrieval_zero_docs metric when search returns empty list."""
    from telegram_bot.agents.rag_pipeline import _hybrid_retrieve

    mock_qdrant_empty = AsyncMock()
    mock_qdrant_empty.hybrid_search_rrf = AsyncMock(
        return_value=(
            [],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    with caplog.at_level(logging.INFO):
        await _hybrid_retrieve(
            "test",
            [0.1] * 1024,
            cache=mock_cache,
            sparse_embeddings=mock_sparse,
            qdrant=mock_qdrant_empty,
            colbert_query=None,
            latency_stages={},
        )

    metric_records = [r for r in caplog.records if r.getMessage() == "metric"]
    names = [getattr(r, "metric_name", None) for r in metric_records]
    assert "retrieval_zero_docs" in names


async def test_rag_pipeline_passes_pre_computed_sparse_to_retrieve(mock_cache, mock_sparse):
    """rag_pipeline passes pre_computed_sparse through _cache_check to _hybrid_retrieve."""
    from unittest.mock import AsyncMock

    from telegram_bot.agents.rag_pipeline import rag_pipeline

    dense = [0.1] * 1024
    sparse = {"indices": [3], "values": [0.7]}

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_hybrid_with_colbert = None  # disable colbert
    mock_embeddings.aembed_hybrid = None  # disable hybrid
    mock_embeddings.aembed_colbert_query = None

    mock_qdrant = AsyncMock()
    mock_qdrant.hybrid_search_rrf_colbert = None  # ensure plain RRF path
    mock_qdrant.hybrid_search_rrf = AsyncMock(
        return_value=(
            [{"text": "doc", "score": 0.9, "metadata": {}}],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    result = await rag_pipeline(
        "test query",
        user_id=1,
        session_id="s1",
        query_type="GENERAL",
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        reranker=None,
        pre_computed_embedding=dense,
        pre_computed_sparse=sparse,
    )

    # sparse_embeddings.aembed_query must NOT be called — sparse was pre-computed
    mock_sparse.aembed_query.assert_not_awaited()
    # cache get_sparse_embedding must NOT be called either
    mock_cache.get_sparse_embedding.assert_not_awaited()
    assert result["documents"]
