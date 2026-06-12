"""Runtime behavior tests for RAG API app/lifespan."""

from __future__ import annotations

import json
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# FastAPI is an optional dep; the canonical fast lane (`make test-unit` after
# `uv sync` without extras) does not install it. Skip cleanly instead of
# installing a partial fake module into ``sys.modules`` that could leak into
# later tests calling ``pytest.importorskip("fastapi")`` (#2009 evidence).
pytest.importorskip("fastapi", reason="src.api.main needs FastAPI; install --extra api")
pytestmark = pytest.mark.requires_extras

from src.api.main import app, generic_error_handler, lifespan, query
from src.api.schemas import QueryRequest, QueryResponse
from src.core import AssistantResult


def _response_content(response) -> dict:
    if hasattr(response, "content"):
        return response.content
    return json.loads(response.body.decode("utf-8"))


def _set_core_state() -> object:
    deps = object()
    app.state.core_dependencies = deps
    app.state.collection_name = "test_collection"
    return deps


def _assistant_result(**overrides) -> AssistantResult:
    data = {
        "response_text": "ok",
        "request_type": "GENERAL",
        "documents_count": 0,
        "cache_hit": False,
        "rerank_applied": False,
        "retrieved_sources": [],
        "route": "rag_search",
    }
    data.update(overrides)
    return AssistantResult(**data)


async def test_query_calls_assistant_core_with_api_context() -> None:
    deps = _set_core_state()
    lf = MagicMock()
    lf.update_current_span = MagicMock()

    with (
        patch("src.observability.propagate_attributes", return_value=nullcontext()),
        patch("src.observability.get_client", return_value=lf),
        patch(
            "src.core.run_assistant_request", new=AsyncMock(return_value=_assistant_result())
        ) as mock_run,
    ):
        await query(QueryRequest(query="test", user_id=1, session_id="sess-1"))

    mock_run.assert_awaited_once()
    call = mock_run.await_args
    assert call.args == ("test",)
    assert call.kwargs["collection"] == "test_collection"
    assert call.kwargs["dependencies"] is deps
    assert call.kwargs["user_context"].user_id == "1"
    assert call.kwargs["user_context"].session_id == "sess-1"


async def test_query_writes_langfuse_scores() -> None:
    """POST /query must call write_langfuse_scores for score parity with bot."""
    _set_core_state()
    lf = MagicMock()
    lf.update_current_span = MagicMock()
    lf.score_current_trace = MagicMock()

    with (
        patch("src.observability.propagate_attributes", return_value=nullcontext()),
        patch("src.observability.get_client", return_value=lf),
        patch("src.core.run_assistant_request", new=AsyncMock(return_value=_assistant_result())),
        patch("src.scoring.write_langfuse_scores") as mock_write_scores,
    ):
        await query(QueryRequest(query="test", user_id=1))

    mock_write_scores.assert_called_once()
    call_args = mock_write_scores.call_args
    assert call_args[0][0] is lf
    assert isinstance(call_args[0][1], dict)


async def test_query_updates_current_observation_and_propagates_api_attributes() -> None:
    """POST /query must propagate correlating attrs and update the active root observation."""
    _set_core_state()
    lf = MagicMock()
    lf.update_current_span = MagicMock()

    with (
        patch(
            "src.observability.propagate_attributes", return_value=nullcontext()
        ) as mock_propagate,
        patch("src.observability.get_client", return_value=lf),
        patch("src.core.run_assistant_request", new=AsyncMock(return_value=_assistant_result())),
    ):
        await query(QueryRequest(query="test", user_id=42, session_id="sess-1", channel="voice"))

    call_kwargs = mock_propagate.call_args.kwargs
    assert call_kwargs["session_id"] == "sess-1"
    assert call_kwargs["user_id"] == "42"
    assert call_kwargs["metadata"]["source"] == "voice"
    assert "request_id" in call_kwargs["metadata"]
    assert call_kwargs["tags"] == ["api", "rag", "voice"]
    assert call_kwargs["as_baggage"] is True
    lf.update_current_span.assert_called_once()
    call_kwargs = lf.update_current_span.call_args.kwargs
    input_payload = call_kwargs["input"]
    assert isinstance(input_payload, dict)
    assert input_payload["content_type"] == "api"
    assert "query_preview" in input_payload
    assert "query_hash" in input_payload
    assert input_payload["query_len"] == 4
    assert "test" not in input_payload
    output_payload = call_kwargs["output"]
    assert isinstance(output_payload, dict)
    assert "answer_preview" in output_payload
    assert "answer_hash" in output_payload
    assert output_payload["answer_len"] == 2
    assert output_payload["chunks_count"] == 1
    assert output_payload["delivery_status"] == "sent"
    assert "ok" not in output_payload
    assert call_kwargs["metadata"]["source"] == "voice"
    assert call_kwargs["metadata"]["query_type"] == "GENERAL"


async def test_query_propagates_explicit_langfuse_trace_id() -> None:
    """POST /query should normalize external ids before opening the root observation."""
    lf = MagicMock()
    lf.create_trace_id.return_value = "0123456789abcdef0123456789abcdef"
    lf.start_as_current_observation.return_value = nullcontext()

    with (
        patch("src.observability.get_client", return_value=lf),
        patch(
            "src.api.main._execute_query",
            new=AsyncMock(return_value=SimpleNamespace()),
        ) as mock_execute,
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

    lf.create_trace_id.assert_called_once_with(seed="trace-123")
    lf.start_as_current_observation.assert_called_once_with(
        as_type="span",
        name="rag-api-query",
        trace_context={"trace_id": "0123456789abcdef0123456789abcdef"},
    )
    mock_execute.assert_awaited_once()


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
    with (
        patch("src.runtime.graph.config.GraphConfig.from_env", return_value=fake_cfg),
        patch("src.runtime.integrations.cache.CacheLayerManager", return_value=fake_cache),
        patch("src.runtime.services.qdrant.QdrantService", return_value=fake_qdrant),
    ):
        async with lifespan(app):
            assert app.state.max_rewrite_attempts == 2
            assert app.state.core_dependencies.reranker is None
            assert app.state.collection_name == "test_collection"


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
    with (
        patch("src.runtime.graph.config.GraphConfig.from_env", return_value=fake_cfg),
        patch("src.runtime.integrations.cache.CacheLayerManager", return_value=fake_cache),
        patch("src.runtime.services.qdrant.QdrantService", return_value=fake_qdrant),
    ):
        async with lifespan(app):
            assert app.state.max_rewrite_attempts == 2
            assert app.state.core_dependencies.reranker is None
            assert app.state.collection_name == "test_collection"


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
    with (
        patch("src.runtime.graph.config.GraphConfig.from_env", return_value=fake_cfg),
        patch("src.runtime.integrations.cache.CacheLayerManager", return_value=fake_cache),
        patch("src.runtime.services.qdrant.QdrantService", return_value=fake_qdrant),
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
        patch("src.observability.get_client", return_value=None),
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


async def test_generic_error_handler_uses_langfuse_trace_id_when_available() -> None:
    """If a Langfuse trace is active, its trace id should be exposed to the client."""
    mock_lf = MagicMock()
    mock_lf.get_current_trace_id.return_value = "trace-abc-123"

    with (
        patch("src.observability.get_client", return_value=mock_lf),
        patch("src.api.main.logger") as mock_logger,
    ):
        response = await generic_error_handler(None, ValueError("bad input"))

    assert _response_content(response)["trace_id"] == "trace-abc-123"
    mock_logger.exception.assert_called_once_with(
        "Unhandled error in RAG API", extra={"trace_id": "trace-abc-123"}
    )


async def test_query_returns_core_error_response() -> None:
    """Core errors should return a valid QueryResponse fallback, not 500."""
    _set_core_state()
    lf = MagicMock()
    lf.update_current_span = MagicMock()
    core_error = _assistant_result(
        response_text="Сервис временно недоступен.",
        request_type="ERROR",
        route="error",
        error_type="dependency_failed",
        documents_count=0,
    )

    with (
        patch("src.observability.propagate_attributes", return_value=nullcontext()),
        patch("src.observability.get_client", return_value=lf),
        patch("src.core.run_assistant_request", new=AsyncMock(return_value=core_error)),
        patch("src.scoring.write_langfuse_scores") as mock_write_scores,
    ):
        response = await query(QueryRequest(query="test", user_id=1))

    assert isinstance(response, QueryResponse)
    assert response.query_type == "ERROR"
    assert response.documents_count == 0
    assert response.latency_ms >= 0
    assert response.response
    lf.update_current_span.assert_called_once()
    mock_write_scores.assert_called_once()


async def test_query_core_error_preserves_trace_context() -> None:
    """Core error fallback should preserve trace/span behavior."""
    _set_core_state()
    lf = MagicMock()
    lf.update_current_span = MagicMock()
    core_error = _assistant_result(
        response_text="Сервис временно недоступен.",
        request_type="ERROR",
        route="error",
        error_type="dependency_failed",
        documents_count=0,
    )

    with (
        patch("src.observability.propagate_attributes", return_value=nullcontext()),
        patch("src.observability.get_client", return_value=lf),
        patch("src.core.run_assistant_request", new=AsyncMock(return_value=core_error)),
    ):
        await query(QueryRequest(query="complex", user_id=42, session_id="sess-1"))

    call_kwargs = lf.update_current_span.call_args.kwargs
    input_payload = call_kwargs["input"]
    assert isinstance(input_payload, dict)
    assert input_payload["content_type"] == "api"
    assert "query_preview" in input_payload
    assert "query_hash" in input_payload
    assert input_payload["query_len"] == 7
    assert "complex" not in input_payload
    output_payload = call_kwargs["output"]
    assert isinstance(output_payload, dict)
    assert "answer_preview" in output_payload
    assert "answer_hash" in output_payload
    assert output_payload["fallback_reason"] == "dependency_failed"
    assert output_payload["chunks_count"] == 1
    assert call_kwargs["metadata"]["source"] == "api"
    assert call_kwargs["metadata"]["query_type"] == "ERROR"


async def test_query_core_error_works_when_langfuse_disabled() -> None:
    """Core error fallback must not crash when Langfuse is disabled."""
    _set_core_state()
    core_error = _assistant_result(
        response_text="Сервис временно недоступен.",
        request_type="ERROR",
        route="error",
        error_type="dependency_failed",
        documents_count=0,
    )

    with (
        patch("src.observability.propagate_attributes", return_value=nullcontext()),
        patch("src.observability.get_client", return_value=None),
        patch("src.core.run_assistant_request", new=AsyncMock(return_value=core_error)),
        patch("src.scoring.write_langfuse_scores") as mock_write_scores,
    ):
        response = await query(QueryRequest(query="test", user_id=1))

    assert isinstance(response, QueryResponse)
    assert response.query_type == "ERROR"
    assert response.documents_count == 0
    assert response.cache_hit is False
    assert response.latency_ms >= 0
    assert response.response
    mock_write_scores.assert_not_called()
