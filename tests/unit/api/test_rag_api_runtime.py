"""Runtime behavior tests for RAG API app/lifespan."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


# FastAPI is an optional dep; the canonical fast lane (`make test-unit` after
# `uv sync` without extras) does not install it. Skip cleanly instead of
# installing a partial fake module into ``sys.modules`` that could leak into
# later tests calling ``pytest.importorskip("fastapi")`` (#2009 evidence).
pytest.importorskip("fastapi", reason="src.api.main needs FastAPI; install --extra api")
pytestmark = pytest.mark.requires_extras

from src.api.main import app, generic_error_handler, lifespan, query
from src.api.schemas import QueryRequest, QueryResponse


def _response_content(response) -> dict:
    if hasattr(response, "content"):
        return response.content
    return json.loads(response.body.decode("utf-8"))


async def _deep_health() -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/health?deep=true")


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

    await query(QueryRequest(query="test", user_id=1))

    assert graph.last_state is not None
    assert graph.last_state["max_rewrite_attempts"] == 3


async def test_query_writes_langfuse_scores() -> None:
    """POST /query must call write_pipeline_scores for score parity with bot."""
    graph = _DummyGraph()
    app.state.graph = graph
    app.state.max_rewrite_attempts = 1

    with patch("src.scoring.write_pipeline_scores") as mock_write_scores:
        await query(QueryRequest(query="test", user_id=1))

    # Tracing removed (#2844): client arg is always None; result dict is still passed.
    mock_write_scores.assert_called_once()
    call_args = mock_write_scores.call_args
    assert call_args[0][0] is None
    assert isinstance(call_args[0][1], dict)


async def test_query_returns_response_for_channel_and_session() -> None:
    """POST /query accepts channel/session fields and returns a normal response."""
    graph = _DummyGraph()
    app.state.graph = graph
    app.state.max_rewrite_attempts = 1

    response = await query(
        QueryRequest(query="test", user_id=42, session_id="sess-1", channel="voice")
    )

    assert isinstance(response, QueryResponse)
    assert response.response == "ok"
    assert response.query_type == "GENERAL"
    assert response.cache_hit is False
    assert response.documents_count == 0
    assert response.rerank_applied is False
    assert response.latency_ms >= 0
    assert graph.last_state is not None
    assert graph.last_state["user_id"] == 42
    assert graph.last_state["session_id"] == "sess-1"


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
        patch("src.runtime.graph.config.GraphConfig.from_env", return_value=fake_cfg),
        patch("src.runtime.integrations.cache.CacheLayerManager", return_value=fake_cache),
        patch("src.runtime.services.qdrant.QdrantService", return_value=fake_qdrant),
        patch(
            "src.runtime.graph.builder.build_pipeline", return_value=fake_graph
        ) as mock_build_pipeline,
    ):
        async with lifespan(app):
            assert app.state.max_rewrite_attempts == 2

    assert mock_build_pipeline.call_args.kwargs["reranker"] is None


async def test_lifespan_keeps_colbert_runtime_server_side() -> None:
    fake_cfg = SimpleNamespace(
        redis_url="redis://localhost:6379",
        cache_thresholds={"GENERAL": 0.08},
        cache_ttl={"GENERAL": 3600},
        qdrant_url="http://qdrant:6333",
        qdrant_collection="test_collection",
        bge_m3_url="http://bge-m3:8000",
        rerank_provider="colbert",
        max_rewrite_attempts=2,
    )
    fake_cfg.create_embeddings = MagicMock(return_value=SimpleNamespace())
    fake_cfg.create_sparse_embeddings = MagicMock(return_value=SimpleNamespace())
    fake_cfg.create_llm = MagicMock(return_value=MagicMock())

    fake_cache = AsyncMock()
    fake_qdrant = AsyncMock()
    fake_graph = MagicMock()

    with (
        patch("src.runtime.graph.config.GraphConfig.from_env", return_value=fake_cfg),
        patch("src.runtime.integrations.cache.CacheLayerManager", return_value=fake_cache),
        patch("src.runtime.services.qdrant.QdrantService", return_value=fake_qdrant),
        patch(
            "src.runtime.graph.builder.build_pipeline", return_value=fake_graph
        ) as mock_build_pipeline,
    ):
        async with lifespan(app):
            assert app.state.max_rewrite_attempts == 2

    assert mock_build_pipeline.call_args.kwargs["reranker"] is None


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
        max_rewrite_attempts=2,
    )
    fake_cfg.create_embeddings = MagicMock(return_value=closable_embeddings)
    fake_cfg.create_sparse_embeddings = MagicMock(return_value=closable_sparse)
    fake_cfg.create_llm = MagicMock(return_value=MagicMock())

    fake_cache = AsyncMock()
    fake_qdrant = AsyncMock()
    fake_graph = MagicMock()

    with (
        patch("src.runtime.graph.config.GraphConfig.from_env", return_value=fake_cfg),
        patch("src.runtime.integrations.cache.CacheLayerManager", return_value=fake_cache),
        patch("src.runtime.services.qdrant.QdrantService", return_value=fake_qdrant),
        patch("src.runtime.graph.builder.build_pipeline", return_value=fake_graph),
        patch("src.api.main.logger.warning") as mock_warning,
    ):
        async with lifespan(app):
            pass

    mock_warning.assert_called_once()
    closable_embeddings.aclose.assert_awaited_once()
    closable_sparse.aclose.assert_awaited_once()


async def test_generic_error_handler_returns_structured_payload() -> None:
    """Unhandled exceptions must return a stable structured error with trace id."""
    with (
        patch("src.api.main.uuid.uuid4", return_value=SimpleNamespace(hex="fallback-trace-id")),
        patch("src.api.main.logger") as mock_logger,
    ):
        response = await generic_error_handler(None, RuntimeError("boom"))

    assert response.status_code == 500
    content = _response_content(response)
    assert content["error"] == "internal_error"
    assert content["message"] == "Internal server error"
    assert content["recoverable"] is False
    assert content["trace_id"] == "fallback-trace-id"
    mock_logger.exception.assert_called_once_with(
        "Unhandled error in RAG API", extra={"trace_id": "fallback-trace-id"}
    )


async def test_query_returns_fallback_on_graph_recursion_error() -> None:
    """GraphRecursionError must return a valid QueryResponse fallback, not 500."""
    from langgraph.errors import GraphRecursionError

    class _FailingGraph:
        async def ainvoke(self, state: dict) -> dict:
            raise GraphRecursionError("recursion limit exceeded")

    app.state.graph = _FailingGraph()
    app.state.max_rewrite_attempts = 1

    with patch("src.scoring.write_pipeline_scores") as mock_write_scores:
        response = await query(QueryRequest(query="test", user_id=1))

    assert isinstance(response, QueryResponse)
    assert "лимит" in response.response.lower() or "limit" in response.response.lower()
    assert response.query_type == "ERROR"
    assert response.documents_count == 0
    assert response.latency_ms >= 0
    mock_write_scores.assert_called_once()
    assert mock_write_scores.call_args[0][0] is None
    assert isinstance(mock_write_scores.call_args[0][1], dict)
    assert mock_write_scores.call_args[0][1]["query_type"] == "ERROR"


async def test_query_graph_recursion_error_preserves_fallback_contract() -> None:
    """GraphRecursionError fallback must keep ERROR contract fields stable."""
    from langgraph.errors import GraphRecursionError

    class _FailingGraph:
        async def ainvoke(self, state: dict) -> dict:
            raise GraphRecursionError("recursion limit exceeded")

    app.state.graph = _FailingGraph()
    app.state.max_rewrite_attempts = 1

    with patch("src.scoring.write_pipeline_scores") as mock_write_scores:
        response = await query(QueryRequest(query="complex", user_id=42, session_id="sess-1"))

    assert isinstance(response, QueryResponse)
    assert response.query_type == "ERROR"
    assert response.cache_hit is False
    assert response.documents_count == 0
    assert response.rerank_applied is False
    assert response.latency_ms >= 0
    assert "лимит" in response.response.lower() or "limit" in response.response.lower()
    mock_write_scores.assert_called_once()
    scored = mock_write_scores.call_args[0][1]
    assert scored["query_type"] == "ERROR"
    assert scored["cache_hit"] is False
    assert scored["search_results_count"] == 0
    assert scored["response"] == response.response


async def test_query_graph_recursion_error_works_when_langfuse_disabled() -> None:
    """Regression for #1606: GraphRecursionError fallback must not crash when
    tracing is disabled (write_pipeline_scores receives lf=None)."""
    from langgraph.errors import GraphRecursionError

    class _FailingGraph:
        async def ainvoke(self, state: dict) -> dict:
            raise GraphRecursionError("recursion limit exceeded")

    app.state.graph = _FailingGraph()
    app.state.max_rewrite_attempts = 1

    with patch("src.scoring.write_pipeline_scores") as mock_write_scores:
        response = await query(QueryRequest(query="test", user_id=1))

    # Must return a valid QueryResponse with the fallback message
    assert isinstance(response, QueryResponse)
    assert response.query_type == "ERROR"
    assert response.documents_count == 0
    assert response.cache_hit is False
    assert response.latency_ms >= 0
    assert response.response  # non-empty fallback message
    assert "лимит" in response.response.lower() or "limit" in response.response.lower()
    # Tracing removed: scores helper is still invoked with lf=None
    mock_write_scores.assert_called_once()
    assert mock_write_scores.call_args[0][0] is None


@pytest.mark.parametrize(
    ("component", "secret"),
    [
        ("cache", "redis://:redis-secret@cache.internal:6379/0"),
        ("qdrant", "https://qdrant-secret@qdrant.internal:6333"),
    ],
)
async def test_health_route_redacts_backend_failure_details(
    monkeypatch: pytest.MonkeyPatch, component: str, secret: str
) -> None:
    cache = SimpleNamespace(ping=AsyncMock(return_value=True))
    qdrant = SimpleNamespace(health=AsyncMock(return_value=None))
    if component == "cache":
        cache.ping.side_effect = RuntimeError(secret)
    else:
        qdrant.health.side_effect = RuntimeError(secret)
    monkeypatch.setattr(app.state, "cache", cache, raising=False)
    monkeypatch.setattr(app.state, "qdrant", qdrant, raising=False)

    with (
        patch("src.api.main._resolve_trace_id", return_value=f"{component}-trace-id"),
        patch("src.api.main.logger") as mock_logger,
    ):
        response = await _deep_health()

    payload = response.json()
    component_payload = payload["components"][component]
    assert response.status_code == 503
    assert component_payload == {"status": "error", "trace_id": f"{component}-trace-id"}
    assert secret not in response.text
    assert mock_logger.exception.call_args.kwargs["extra"] == {"trace_id": f"{component}-trace-id"}


async def test_health_route_exposes_qdrant_quantization_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        app.state, "cache", SimpleNamespace(ping=AsyncMock(return_value=True)), raising=False
    )
    monkeypatch.setattr(
        app.state,
        "qdrant",
        SimpleNamespace(
            quantization_degraded=True,
            requested_quantization_mode="binary",
            quantization_mode="off",
        ),
        raising=False,
    )

    response = await _deep_health()

    assert response.status_code == 503
    assert response.json()["components"]["qdrant"] == {
        "status": "degraded",
        "requested_quantization_mode": "binary",
        "effective_quantization_mode": "off",
    }
