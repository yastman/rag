"""Tests for performance fixes #951, #953, #955."""

from __future__ import annotations

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
    from src.runtime.pipeline.rag import rag_pipeline

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
    from src.runtime.pipeline.rag import rag_pipeline

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


async def test_warmup_bge_calls_hybrid_embed():
    """#953: _warmup_bge() should call _hybrid.aembed_query('warmup')."""
    import sys
    from unittest.mock import MagicMock as _MagicMock

    # Mock the problematic import chain before importing PropertyBot
    _mocked = {}
    for mod in (
        "src.retrieval",
        "src.retrieval.topic_classifier",
        "src.retrieval.search_engines",
        "src.retrieval.search_engine_shared",
    ):
        if mod not in sys.modules:
            _mocked[mod] = sys.modules.setdefault(mod, _MagicMock())

    try:
        from telegram_bot.bot import PropertyBot

        bot = object.__new__(PropertyBot)
        bot._hybrid = AsyncMock()
        bot._hybrid.aembed_query = AsyncMock(return_value=[0.1] * 1024)

        await bot._warmup_bge()

        bot._hybrid.aembed_query.assert_called_once_with("warmup")
    finally:
        for mod in _mocked:
            sys.modules.pop(mod, None)


async def test_warmup_bge_failure_nonfatal():
    """#953: BGE-M3 warmup failure should not prevent bot startup."""
    import sys
    from unittest.mock import MagicMock as _MagicMock

    _mocked = {}
    for mod in (
        "src.retrieval",
        "src.retrieval.topic_classifier",
        "src.retrieval.search_engines",
        "src.retrieval.search_engine_shared",
    ):
        if mod not in sys.modules:
            _mocked[mod] = sys.modules.setdefault(mod, _MagicMock())

    try:
        from telegram_bot.bot import PropertyBot

        bot = object.__new__(PropertyBot)
        bot._hybrid = AsyncMock()
        bot._hybrid.aembed_query = AsyncMock(side_effect=ConnectionError("BGE-M3 down"))

        # Should not raise
        await bot._warmup_bge()

        bot._hybrid.aembed_query.assert_called_once_with("warmup")
    finally:
        for mod in _mocked:
            sys.modules.pop(mod, None)


# ---------------------------------------------------------------------------
# #955: Score stubs are no-ops (Langfuse removed in #2844)
# ---------------------------------------------------------------------------


def test_write_scores_is_noop():
    """write_scores is a no-op — Langfuse removed (#2844)."""
    from src.scoring import write_scores

    lf = MagicMock()
    result = {"pipeline_wall_ms": 1500.0, "search_results_count": 20, "latency_stages": {}}
    write_scores(lf, result, trace_id="t1")
    lf.create_score.assert_not_called()
