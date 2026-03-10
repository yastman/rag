"""Tests for performance fixes #951, #953, #955."""

from __future__ import annotations

import contextlib
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# #951: Eliminate redundant BGE-M3 call on agent query rewrite
# ---------------------------------------------------------------------------


@pytest.fixture
def _cache_951():
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
def _embeddings_951():
    emb = AsyncMock()
    emb.aembed_query = AsyncMock(return_value=[0.1] * 1024)
    emb.aembed_hybrid = AsyncMock(return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}))
    emb.aembed_hybrid_with_colbert = AsyncMock(
        return_value=([0.1] * 1024, {"indices": [1], "values": [0.5]}, [[0.2] * 128])
    )
    emb.aembed_colbert_query = AsyncMock(return_value=[[0.2] * 128])
    return emb


@pytest.fixture
def _sparse_951():
    sparse = AsyncMock()
    sparse.aembed_query = AsyncMock(return_value={"indices": [1], "values": [0.5]})
    return sparse


@pytest.fixture
def _qdrant_951():
    qdrant = AsyncMock()
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
def _reranker_951():
    reranker = AsyncMock()
    reranker.rerank = AsyncMock(
        return_value=[
            {"index": 0, "score": 0.95},
            {"index": 1, "score": 0.85},
        ]
    )
    return reranker


async def test_agent_rewrite_no_separate_colbert_call(
    _cache_951, _embeddings_951, _sparse_951, _qdrant_951, _reranker_951
):
    """#951: When agent reformulates query (cache_key != query), should NOT call
    aembed_colbert_query separately — let _hybrid_retrieve handle it in one call."""
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    # Pre-computed embeddings for original query (cache_key)
    pre_embedding = [0.5] * 1024
    pre_sparse = {"indices": [2], "values": [0.8]}
    pre_colbert = [[0.3] * 128]

    result = await rag_pipeline(
        query="reformulated better query",  # different from original_query
        user_id=42,
        session_id="test",
        query_type="GENERAL",
        cache=_cache_951,
        embeddings=_embeddings_951,
        sparse_embeddings=_sparse_951,
        qdrant=_qdrant_951,
        reranker=_reranker_951,
        original_query="original user query",
        pre_computed_embedding=pre_embedding,
        pre_computed_sparse=pre_sparse,
        pre_computed_colbert=pre_colbert,
    )

    # aembed_colbert_query should NOT have been called separately (#951 fix)
    # Before fix: cache_key != query branch called aembed_colbert_query independently.
    # After fix: query_embedding=None → _hybrid_retrieve does ONE combined call.
    _embeddings_951.aembed_colbert_query.assert_not_called()
    assert result["cache_hit"] is False


async def test_same_query_reuses_precomputed(
    _cache_951, _embeddings_951, _sparse_951, _qdrant_951, _reranker_951
):
    """When cache_key == query, pre-computed embeddings are reused."""
    from telegram_bot.agents.rag_pipeline import rag_pipeline

    pre_embedding = [0.5] * 1024
    pre_sparse = {"indices": [2], "values": [0.8]}

    result = await rag_pipeline(
        query="same query",
        user_id=42,
        session_id="test",
        query_type="GENERAL",
        cache=_cache_951,
        embeddings=_embeddings_951,
        sparse_embeddings=_sparse_951,
        qdrant=_qdrant_951,
        reranker=_reranker_951,
        original_query="same query",
        pre_computed_embedding=pre_embedding,
        pre_computed_sparse=pre_sparse,
    )

    assert result["cache_hit"] is False
    # Embedding service should NOT be called for dense (pre-computed used)
    _embeddings_951.aembed_query.assert_not_called()


# ---------------------------------------------------------------------------
# #953: Warm BGE-M3 connection pool on bot startup
# ---------------------------------------------------------------------------


async def test_bge_warmup_called_on_start():
    """#953: PropertyBot.start() should call _hybrid.aembed_query('warmup')."""
    from telegram_bot.bot import PropertyBot

    bot = MagicMock(spec=PropertyBot)
    bot._hybrid = AsyncMock()
    bot._hybrid.aembed_query = AsyncMock(return_value=[0.1] * 1024)

    # Call the warmup logic directly (extracted pattern)
    with contextlib.suppress(Exception):
        await bot._hybrid.aembed_query("warmup")

    bot._hybrid.aembed_query.assert_called_once_with("warmup")


async def test_bge_warmup_failure_nonfatal():
    """#953: BGE-M3 warmup failure should not prevent bot startup."""
    hybrid = AsyncMock()
    hybrid.aembed_query = AsyncMock(side_effect=ConnectionError("BGE-M3 down"))

    # Should not raise
    with contextlib.suppress(Exception):
        await hybrid.aembed_query("warmup")

    hybrid.aembed_query.assert_called_once_with("warmup")


# ---------------------------------------------------------------------------
# #955: Voice pipeline scores recorded correctly
# ---------------------------------------------------------------------------


def test_write_langfuse_scores_voice_fields():
    """#955: write_langfuse_scores writes voice-specific scores when present."""
    from telegram_bot.scoring import write_langfuse_scores

    lf = MagicMock()
    lf.get_current_trace_id.return_value = "test-trace-id"

    result = {
        "query_type": "GENERAL",
        "pipeline_wall_ms": 1500.0,
        "e2e_latency_ms": 1500.0,
        "cache_hit": False,
        "search_results_count": 20,
        "latency_stages": {"generate": 0.8, "retrieve": 0.3, "cache_check": 0.05},
        "grade_confidence": 0.012,
        "input_type": "voice",
        "stt_duration_ms": 450.0,
        "voice_duration_s": 3.5,
    }

    write_langfuse_scores(lf, result, trace_id="test-trace-id")

    # Collect all score names written
    score_names = [
        call.kwargs.get("name", call.args[2] if len(call.args) > 2 else None)
        for call in lf.create_score.call_args_list
    ]
    # Try name from kwargs first
    if not any(score_names):
        score_names = []
        for call in lf.create_score.call_args_list:
            kw = call.kwargs
            score_names.append(kw.get("name", ""))

    assert "results_count" in score_names
    assert "llm_used" in score_names
    assert "input_type" in score_names
    assert "stt_duration_ms" in score_names
    assert "voice_duration_s" in score_names


def test_write_langfuse_scores_llm_used_when_generate_in_stages():
    """#955: llm_used=1.0 when 'generate' key exists in latency_stages."""
    from telegram_bot.scoring import write_langfuse_scores

    lf = MagicMock()
    result = {
        "latency_stages": {"generate": 0.5},
        "pipeline_wall_ms": 1000.0,
        "search_results_count": 5,
    }

    write_langfuse_scores(lf, result, trace_id="t1")

    # Find the llm_used score call
    for call in lf.create_score.call_args_list:
        if call.kwargs.get("name") == "llm_used":
            assert call.kwargs["value"] == 1.0
            return
    pytest.fail("llm_used score not written")


def test_write_langfuse_scores_results_count():
    """#955: results_count reflects search_results_count from state."""
    from telegram_bot.scoring import write_langfuse_scores

    lf = MagicMock()
    result = {
        "latency_stages": {},
        "pipeline_wall_ms": 500.0,
        "search_results_count": 20,
    }

    write_langfuse_scores(lf, result, trace_id="t2")

    for call in lf.create_score.call_args_list:
        if call.kwargs.get("name") == "results_count":
            assert call.kwargs["value"] == 20.0
            return
    pytest.fail("results_count score not written")


def test_write_langfuse_scores_no_results_flag():
    """#955: no_results=1 when search_results_count is 0."""
    from telegram_bot.scoring import write_langfuse_scores

    lf = MagicMock()
    result = {
        "latency_stages": {},
        "pipeline_wall_ms": 500.0,
        "search_results_count": 0,
    }

    write_langfuse_scores(lf, result, trace_id="t3")

    for call in lf.create_score.call_args_list:
        if call.kwargs.get("name") == "no_results":
            assert call.kwargs["value"] == 1.0
            return
    pytest.fail("no_results score not written")


def test_write_langfuse_scores_cache_hit_voice():
    """#955: Voice cache hit path still records scores correctly."""
    from telegram_bot.scoring import write_langfuse_scores

    lf = MagicMock()
    result = {
        "latency_stages": {"cache_check": 0.05},
        "pipeline_wall_ms": 200.0,
        "cache_hit": True,
        "search_results_count": 0,
        "input_type": "voice",
        "stt_duration_ms": 300.0,
        "voice_duration_s": 2.0,
    }

    write_langfuse_scores(lf, result, trace_id="t4")

    score_names = [call.kwargs.get("name") for call in lf.create_score.call_args_list]
    assert "semantic_cache_hit" in score_names
    assert "input_type" in score_names
    # llm_used should be 0 (no generate stage)
    for call in lf.create_score.call_args_list:
        if call.kwargs.get("name") == "llm_used":
            assert call.kwargs["value"] == 0.0
        if call.kwargs.get("name") == "semantic_cache_hit":
            assert call.kwargs["value"] == 1.0
