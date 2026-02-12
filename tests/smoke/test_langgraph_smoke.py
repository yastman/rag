# tests/smoke/test_langgraph_smoke.py
"""Smoke tests for LangGraph RAG pipeline.

Verifies graph assembly and invocation with mocked services.
For live-service E2E, use tests/smoke/test_smoke_services.py.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.graph.graph import build_graph
from telegram_bot.graph.state import make_initial_state
from telegram_bot.observability import traced_pipeline


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
    assert state["messages"][0]["content"] == "test"


@pytest.mark.smoke
async def test_full_graph_classify_to_respond():
    """E2E: mock services, full graph pipeline from classify to respond."""
    # Cache — all async methods must be AsyncMock
    mock_cache = MagicMock()
    mock_cache.get_embedding = AsyncMock(return_value=None)
    mock_cache.store_embedding = AsyncMock()
    mock_cache.check_semantic = AsyncMock(return_value=None)
    mock_cache.store_semantic = AsyncMock()
    mock_cache.get_search_results = AsyncMock(return_value=None)
    mock_cache.store_search_results = AsyncMock()
    mock_cache.get_sparse_embedding = AsyncMock(return_value=None)
    mock_cache.store_sparse_embedding = AsyncMock()

    # Embeddings
    mock_embeddings = MagicMock()
    mock_embeddings.aembed_query = AsyncMock(return_value=[0.1] * 1024)

    # Sparse embeddings
    mock_sparse = MagicMock()
    mock_sparse.aembed_query = AsyncMock(
        return_value={"indices": [1, 5, 10], "values": [0.5, 0.3, 0.2]}
    )

    # Qdrant
    mock_qdrant = MagicMock()
    mock_qdrant.hybrid_search_rrf = AsyncMock(
        return_value=(
            [
                {"text": "Квартира в Несебр, 85000 евро", "score": 0.9, "id": "1"},
                {"text": "Студия в Солнечный берег, 60000 евро", "score": 0.85, "id": "2"},
            ],
            {"backend_error": False, "error_type": None, "error_message": None},
        )
    )

    # LLM mock (OpenAI SDK pattern: llm.chat.completions.create)
    mock_llm = MagicMock()
    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock(message=MagicMock(content="Найдено 2 варианта."))]
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_completion)

    # Telegram message for respond_node
    mock_message = MagicMock()
    mock_message.answer = AsyncMock()
    mock_message.chat = MagicMock()
    mock_message.chat.id = 12345

    graph = build_graph(
        cache=mock_cache,
        embeddings=mock_embeddings,
        sparse_embeddings=mock_sparse,
        qdrant=mock_qdrant,
        reranker=None,
        llm=mock_llm,
        message=mock_message,
    )

    state = make_initial_state(
        user_id=42,
        session_id="smoke-test-20260209",
        query="квартиры в Несебр до 100000 евро",
    )

    # Patch generate_node's internal config to use our mock LLM
    mock_gc = MagicMock()
    mock_gc.create_llm.return_value = mock_llm
    mock_gc.domain = "недвижимость"
    mock_gc.llm_model = "gpt-4o-mini"
    mock_gc.llm_temperature = 0.7
    mock_gc.llm_max_tokens = 4096

    with traced_pipeline(session_id="smoke-test-20260209", user_id="smoke"):
        with patch(
            "telegram_bot.graph.nodes.generate._get_config",
            return_value=mock_gc,
        ):
            result = await graph.ainvoke(state)

    # Graph should produce a response
    assert "response" in result
    assert result["response"]  # non-empty
