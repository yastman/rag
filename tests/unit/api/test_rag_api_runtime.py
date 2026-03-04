"""Runtime behavior tests for RAG API app/lifespan."""

from __future__ import annotations

import importlib.util
import sys
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch


_FASTAPI_SHIM_ACTIVE = False
if importlib.util.find_spec("fastapi") is None:
    # Minimal shim so src.api.main can be imported in core unit CI.
    class _FakeJSONResponse:
        def __init__(self, *, status_code: int, content: dict) -> None:
            self.status_code = status_code
            self.content = content

    class _FakeFastAPI:
        def __init__(self, *args, **kwargs) -> None:
            self.state = SimpleNamespace()

        def exception_handler(self, *_args, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

        def get(self, *_args, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

        def post(self, *_args, **_kwargs):
            def _decorator(func):
                return func

            return _decorator

    fake_fastapi = type(sys)("fastapi")
    fake_fastapi.FastAPI = _FakeFastAPI
    fake_fastapi_responses = type(sys)("fastapi.responses")
    fake_fastapi_responses.JSONResponse = _FakeJSONResponse
    sys.modules["fastapi"] = fake_fastapi
    sys.modules["fastapi.responses"] = fake_fastapi_responses
    _FASTAPI_SHIM_ACTIVE = True

from src.api.main import app, lifespan, query
from src.api.schemas import QueryRequest


if _FASTAPI_SHIM_ACTIVE:
    # Prevent leaking shim into other tests that intentionally importorskip fastapi.
    sys.modules.pop("fastapi.responses", None)
    sys.modules.pop("fastapi", None)


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


async def test_query_observe_trace_sets_api_tags_and_ids() -> None:
    """POST /query must set trace tags ["api", "rag", channel] and session/user IDs."""
    graph = _DummyGraph()
    app.state.graph = graph
    app.state.max_rewrite_attempts = 1

    lf = MagicMock()
    lf.update_current_trace = MagicMock()

    with (
        patch("telegram_bot.observability.propagate_attributes", return_value=nullcontext()),
        patch("telegram_bot.observability.get_client", return_value=lf),
    ):
        await query(QueryRequest(query="test", user_id=42, session_id="sess-1", channel="voice"))

    lf.update_current_trace.assert_called_once()
    call_kwargs = lf.update_current_trace.call_args.kwargs
    assert "tags" in call_kwargs
    assert "api" in call_kwargs["tags"]
    assert "rag" in call_kwargs["tags"]
    assert "voice" in call_kwargs["tags"]
    assert call_kwargs["session_id"] == "sess-1"
    assert call_kwargs["user_id"] == "42"


async def test_query_propagates_explicit_langfuse_trace_id() -> None:
    """POST /query should forward explicit trace id into propagate_attributes."""
    graph = _DummyGraph()
    app.state.graph = graph
    app.state.max_rewrite_attempts = 1

    lf = MagicMock()
    lf.update_current_trace = MagicMock()

    with (
        patch(
            "telegram_bot.observability.propagate_attributes", return_value=nullcontext()
        ) as mock_propagate,
        patch("telegram_bot.observability.get_client", return_value=lf),
    ):
        await query(
            QueryRequest(
                query="test",
                user_id=42,
                session_id="sess-1",
                channel="voice",
                langfuse_trace_id="trace-123",
            )
        )

    assert mock_propagate.call_args.kwargs["trace_id"] == "trace-123"


async def test_lifespan_respects_rerank_provider_none() -> None:
    fake_cfg = SimpleNamespace(
        redis_url="redis://localhost:6379",
        cache_thresholds={"GENERAL": 0.08},
        cache_ttl={"GENERAL": 3600},
        qdrant_url="http://qdrant:6333",
        qdrant_collection="test_collection",
        bge_m3_url="http://bge-m3:8000",
        rerank_provider="none",
        classifier_mode="regex",
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
    assert mock_build_graph.call_args.kwargs["classifier"] is None
    mock_colbert.assert_not_called()


async def test_lifespan_wires_semantic_classifier_when_enabled() -> None:
    fake_cfg = SimpleNamespace(
        redis_url="redis://localhost:6379",
        cache_thresholds={"GENERAL": 0.08},
        cache_ttl={"GENERAL": 3600},
        qdrant_url="http://qdrant:6333",
        qdrant_collection="test_collection",
        bge_m3_url="http://bge-m3:8000",
        rerank_provider="none",
        classifier_mode="semantic",
        max_rewrite_attempts=2,
    )
    fake_cfg.create_embeddings = MagicMock(return_value=SimpleNamespace())
    fake_cfg.create_sparse_embeddings = MagicMock(return_value=SimpleNamespace())
    fake_cfg.create_llm = MagicMock(return_value=MagicMock())

    fake_cache = AsyncMock()
    fake_qdrant = AsyncMock()
    fake_graph = MagicMock()
    fake_classifier = MagicMock()

    with (
        patch("telegram_bot.graph.config.GraphConfig.from_env", return_value=fake_cfg),
        patch("telegram_bot.integrations.cache.CacheLayerManager", return_value=fake_cache),
        patch("telegram_bot.services.qdrant.QdrantService", return_value=fake_qdrant),
        patch("telegram_bot.graph.graph.build_graph", return_value=fake_graph) as mock_build_graph,
        patch(
            "telegram_bot.services.semantic_classifier.SemanticClassifier",
            return_value=fake_classifier,
        ) as mock_classifier,
        patch("telegram_bot.services.colbert_reranker.ColbertRerankerService") as mock_colbert,
    ):
        async with lifespan(app):
            pass

    mock_classifier.assert_called_once_with(redis_url="redis://localhost:6379")
    assert mock_build_graph.call_args.kwargs["classifier"] is fake_classifier
    mock_colbert.assert_not_called()


async def test_lifespan_unknown_rerank_provider_logs_and_closes_embeddings() -> None:
    closable_embeddings = SimpleNamespace(aclose=AsyncMock())
    closable_sparse = SimpleNamespace(aclose=AsyncMock())
    fake_cfg = SimpleNamespace(
        redis_url="redis://localhost:6379",
        cache_thresholds={"GENERAL": 0.08},
        cache_ttl={"GENERAL": 3600},
        qdrant_url="http://qdrant:6333",
        qdrant_collection="test_collection",
        bge_m3_url="http://bge-m3:8000",
        rerank_provider="mystery",
        classifier_mode="regex",
        max_rewrite_attempts=2,
    )
    fake_cfg.create_embeddings = MagicMock(return_value=closable_embeddings)
    fake_cfg.create_sparse_embeddings = MagicMock(return_value=closable_sparse)
    fake_cfg.create_llm = MagicMock(return_value=MagicMock())

    fake_cache = AsyncMock()
    fake_qdrant = AsyncMock()
    fake_graph = MagicMock()

    with (
        patch("telegram_bot.graph.config.GraphConfig.from_env", return_value=fake_cfg),
        patch("telegram_bot.integrations.cache.CacheLayerManager", return_value=fake_cache),
        patch("telegram_bot.services.qdrant.QdrantService", return_value=fake_qdrant),
        patch("telegram_bot.graph.graph.build_graph", return_value=fake_graph),
        patch("src.api.main.logger.warning") as mock_warning,
    ):
        async with lifespan(app):
            pass

    mock_warning.assert_called_once()
    closable_embeddings.aclose.assert_awaited_once()
    closable_sparse.aclose.assert_awaited_once()
