"""Runtime behavior tests for RAG API app/lifespan."""

from __future__ import annotations

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("fastapi", reason="fastapi not installed (voice extra)")
pytestmark = pytest.mark.requires_extras

from src.api.main import app, lifespan, query
from src.api.schemas import QueryRequest


class _DummyGraph:
    def __init__(self) -> None:
        self.last_state: dict | None = None

    async def ainvoke(self, state: dict) -> dict:
        self.last_state = state
        return {
            "response": "ok",
            "query_type": "GENERAL",
            "cache_hit": False,
            "search_results_count": 0,
            "rerank_applied": False,
        }


async def test_query_applies_max_rewrite_attempts_from_app_state() -> None:
    graph = _DummyGraph()
    app.state.graph = graph
    app.state.max_rewrite_attempts = 3

    lf = MagicMock()
    lf.update_current_trace = MagicMock()

    with (
        patch("telegram_bot.observability.propagate_attributes", return_value=nullcontext()),
        patch("telegram_bot.observability.get_client", return_value=lf),
    ):
        await query(QueryRequest(query="test", user_id=1))

    assert graph.last_state is not None
    assert graph.last_state["max_rewrite_attempts"] == 3


async def test_query_writes_langfuse_scores() -> None:
    """POST /query must call write_langfuse_scores for score parity with bot."""
    graph = _DummyGraph()
    app.state.graph = graph
    app.state.max_rewrite_attempts = 1

    lf = MagicMock()
    lf.update_current_trace = MagicMock()
    lf.score_current_trace = MagicMock()

    with (
        patch("telegram_bot.observability.propagate_attributes", return_value=nullcontext()),
        patch("telegram_bot.observability.get_client", return_value=lf),
        patch("telegram_bot.scoring.write_langfuse_scores") as mock_write_scores,
    ):
        await query(QueryRequest(query="test", user_id=1))

    # write_langfuse_scores must be called with (lf_client, result_state)
    mock_write_scores.assert_called_once()
    call_args = mock_write_scores.call_args
    assert call_args[0][0] is lf  # first arg: langfuse client
    assert isinstance(call_args[0][1], dict)  # second arg: result dict


async def test_lifespan_respects_rerank_provider_none() -> None:
    fake_cfg = SimpleNamespace(
        redis_url="redis://localhost:6379",
        cache_thresholds={"GENERAL": 0.08},
        cache_ttl={"GENERAL": 3600},
        qdrant_url="http://qdrant:6333",
        qdrant_collection="test_collection",
        bge_m3_url="http://bge-m3:8000",
        rerank_provider="none",
        max_rewrite_attempts=2,
    )
    fake_cfg.create_embeddings = MagicMock(return_value=SimpleNamespace())
    fake_cfg.create_sparse_embeddings = MagicMock(return_value=SimpleNamespace())
    fake_cfg.create_llm = MagicMock(return_value=MagicMock())

    fake_cache = AsyncMock()
    fake_qdrant = AsyncMock()
    fake_graph = MagicMock()

    with (
        patch("telegram_bot.graph.config.GraphConfig.from_env", return_value=fake_cfg),
        patch("telegram_bot.integrations.cache.CacheLayerManager", return_value=fake_cache),
        patch("telegram_bot.services.qdrant.QdrantService", return_value=fake_qdrant),
        patch("telegram_bot.graph.graph.build_graph", return_value=fake_graph) as mock_build_graph,
        patch("telegram_bot.services.colbert_reranker.ColbertRerankerService") as mock_colbert,
    ):
        async with lifespan(app):
            assert app.state.max_rewrite_attempts == 2

    assert mock_build_graph.call_args.kwargs["reranker"] is None
    mock_colbert.assert_not_called()
