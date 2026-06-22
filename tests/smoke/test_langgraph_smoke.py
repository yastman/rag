# tests/smoke/test_langgraph_smoke.py
"""Smoke tests for LangGraph RAG pipeline.

Verifies graph assembly and invocation with mocked services.
For live-service E2E, use tests/smoke/test_smoke_services.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.runtime.graph.state import make_initial_state
from telegram_bot.pipelines.graph_compat import build_graph


pytestmark = pytest.mark.no_services


@pytest.mark.smoke
async def test_full_graph_builds_without_error():
    """Graph should compile without errors given mock services."""
    graph = build_graph(
        cache=MagicMock(),
        embeddings=MagicMock(),
        sparse_embeddings=MagicMock(),
        qdrant=MagicMock(),
        reranker=None,
        llm=MagicMock(),
        message=MagicMock(),
    )
    assert graph is not None
    assert hasattr(graph, "ainvoke")


@pytest.mark.smoke
async def test_initial_state_has_required_keys():
    """make_initial_state should produce all required RAGState fields."""
    state = make_initial_state(user_id=123, session_id="smoke-abc-20260209", query="test")
    required = {
        "messages",
        "user_id",
        "session_id",
        "query_type",
        "cache_hit",
        "documents",
        "response",
    }
    assert required.issubset(state.keys())
    assert state["user_id"] == 123
    assert state["session_id"] == "smoke-abc-20260209"
    assert state["messages"][0].content == "test"


@pytest.mark.smoke
async def test_full_graph_classify_to_respond():
    """E2E: mock services, full graph pipeline from classify to respond."""
    from src.core.contracts import AssistantResult

    mock_message = MagicMock()
    mock_message.answer = AsyncMock()

    graph = build_graph(
        cache=MagicMock(),
        embeddings=MagicMock(),
        sparse_embeddings=MagicMock(),
        qdrant=MagicMock(),
        reranker=None,
        llm=MagicMock(),
        message=mock_message,
    )

    state = make_initial_state(
        user_id=42,
        session_id="smoke-test-20260209",
        query="квартиры в Несебр до 100000 евро",
    )

    pipeline_result = AssistantResult(
        response_text="Найдено 2 варианта.",
        route="rag",
        request_type="REAL_ESTATE",
        documents_count=2,
        latency_ms=100.0,
        cache_hit=False,
        rerank_applied=False,
        error_type=None,
    )

    with patch(
        "telegram_bot.pipelines.graph_compat.run_assistant_pipeline",
        new=AsyncMock(return_value=pipeline_result),
    ):
        result = await graph.ainvoke(state)

    # Graph should produce a response
    assert "response" in result
    assert result["response"]  # non-empty
