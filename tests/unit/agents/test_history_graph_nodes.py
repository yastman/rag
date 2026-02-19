"""Tests for history sub-graph nodes (#408)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture()
def mock_history_service():
    svc = AsyncMock()
    svc.search_user_history = AsyncMock(return_value=[])
    return svc


@pytest.fixture()
def _patch_observe():
    """Disable Langfuse @observe for unit tests."""
    with patch("telegram_bot.agents.history_graph.nodes.observe", lambda **_kw: lambda f: f):
        with patch("telegram_bot.agents.history_graph.nodes.get_client") as mock_lf:
            mock_lf.return_value = AsyncMock(
                update_current_span=lambda **_kw: None,
                score_current_trace=lambda **_kw: None,
                create_score=lambda **_kw: None,
                get_current_trace_id=lambda: "test-trace",
            )
            yield mock_lf


# --- retrieve node ---


async def test_retrieve_node_calls_service(mock_history_service, _patch_observe):
    """retrieve_node calls HistoryService.search_user_history with user_id and query."""
    from telegram_bot.agents.history_graph.nodes import history_retrieve_node

    mock_history_service.search_user_history.return_value = [
        {
            "query": "цены",
            "response": "Средние цены...",
            "timestamp": "2026-02-13T10:00",
            "score": 0.92,
        },
    ]
    state = {
        "query": "цены на квартиры",
        "user_id": 42,
        "results": [],
        "results_relevant": False,
        "rewrite_count": 0,
        "max_rewrite_attempts": 1,
        "summary": "",
        "latency_stages": {},
    }
    result = await history_retrieve_node(state, history_service=mock_history_service)

    mock_history_service.search_user_history.assert_called_once_with(
        user_id=42,
        query="цены на квартиры",
        limit=10,
    )
    assert len(result["results"]) == 1
    assert "retrieve" in result["latency_stages"]


async def test_retrieve_node_empty_results(mock_history_service, _patch_observe):
    """retrieve_node returns empty results when nothing found."""
    from telegram_bot.agents.history_graph.nodes import history_retrieve_node

    state = {
        "query": "несуществующий",
        "user_id": 42,
        "results": [],
        "results_relevant": False,
        "rewrite_count": 0,
        "max_rewrite_attempts": 1,
        "summary": "",
        "latency_stages": {},
    }
    result = await history_retrieve_node(state, history_service=mock_history_service)

    assert result["results"] == []


async def test_retrieve_node_service_error_returns_empty(mock_history_service, _patch_observe):
    """Service exception returns empty results, no raise."""
    from telegram_bot.agents.history_graph.nodes import history_retrieve_node

    mock_history_service.search_user_history.side_effect = RuntimeError("DB down")
    state = {
        "query": "test",
        "user_id": 42,
        "results": [],
        "results_relevant": False,
        "rewrite_count": 0,
        "max_rewrite_attempts": 1,
        "summary": "",
        "latency_stages": {},
    }
    result = await history_retrieve_node(state, history_service=mock_history_service)

    assert result["results"] == []


# --- grade node ---

_GRADE_STATE_BASE = {
    "query": "цены",
    "user_id": 42,
    "results_relevant": False,
    "rewrite_count": 0,
    "max_rewrite_attempts": 1,
    "summary": "",
    "latency_stages": {},
}


async def test_grade_node_high_score_relevant(_patch_observe):
    """Results with score > 0.7 are marked relevant."""
    from telegram_bot.agents.history_graph.nodes import history_grade_node

    state = {
        **_GRADE_STATE_BASE,
        "results": [
            {
                "query": "цены",
                "response": "Средние цены...",
                "score": 0.85,
                "timestamp": "2026-02-13T10:00",
            },
        ],
    }
    result = await history_grade_node(state)
    assert result["results_relevant"] is True


async def test_grade_node_low_score_not_relevant(_patch_observe):
    """Results with all scores < 0.7 are marked not relevant."""
    from telegram_bot.agents.history_graph.nodes import history_grade_node

    state = {
        **_GRADE_STATE_BASE,
        "results": [
            {
                "query": "что-то",
                "response": "...",
                "score": 0.3,
                "timestamp": "2026-02-13T10:00",
            },
        ],
    }
    result = await history_grade_node(state)
    assert result["results_relevant"] is False


async def test_grade_node_empty_results(_patch_observe):
    """Empty results → not relevant."""
    from telegram_bot.agents.history_graph.nodes import history_grade_node

    state = {**_GRADE_STATE_BASE, "results": []}
    result = await history_grade_node(state)
    assert result["results_relevant"] is False


async def test_grade_node_filters_low_scores(_patch_observe):
    """Grade node filters out results below threshold."""
    from telegram_bot.agents.history_graph.nodes import history_grade_node

    state = {
        **_GRADE_STATE_BASE,
        "results": [
            {
                "query": "цены",
                "response": "Хорошо...",
                "score": 0.9,
                "timestamp": "2026-02-13T10:00",
            },
            {
                "query": "погода",
                "response": "...",
                "score": 0.3,
                "timestamp": "2026-02-12T10:00",
            },
        ],
    }
    result = await history_grade_node(state)
    assert result["results_relevant"] is True
    # Low-score items filtered
    assert len(result["results"]) == 1


# --- rewrite node ---


async def test_rewrite_node_reformulates_query(_patch_observe):
    """rewrite_node calls LLM to reformulate query."""
    from telegram_bot.agents.history_graph.nodes import history_rewrite_node

    mock_llm = AsyncMock()
    mock_response = AsyncMock()
    mock_response.choices = [AsyncMock(message=AsyncMock(content="цены на квартиры в Варне"))]
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)

    state = {
        "query": "цены",
        "user_id": 42,
        "results": [],
        "results_relevant": False,
        "rewrite_count": 0,
        "max_rewrite_attempts": 1,
        "summary": "",
        "latency_stages": {},
    }
    result = await history_rewrite_node(state, llm=mock_llm)

    assert result["query"] == "цены на квартиры в Варне"
    assert result["rewrite_count"] == 1
    mock_llm.chat.completions.create.assert_called_once()


async def test_rewrite_node_llm_failure_keeps_query(_patch_observe):
    """LLM failure keeps original query."""
    from telegram_bot.agents.history_graph.nodes import history_rewrite_node

    mock_llm = AsyncMock()
    mock_llm.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM down"))

    state = {
        "query": "оригинальный",
        "user_id": 42,
        "results": [],
        "results_relevant": False,
        "rewrite_count": 0,
        "max_rewrite_attempts": 1,
        "summary": "",
        "latency_stages": {},
    }
    result = await history_rewrite_node(state, llm=mock_llm)

    assert result["query"] == "оригинальный"
    assert result["rewrite_count"] == 1


# --- routing ---


def test_route_history_grade_relevant():
    """Relevant results route to summarize."""
    from telegram_bot.agents.history_graph.nodes import route_history_grade

    state = {"results_relevant": True, "rewrite_count": 0, "max_rewrite_attempts": 1}
    assert route_history_grade(state) == "summarize"


def test_route_history_grade_not_relevant_rewrite():
    """Not relevant + rewrites left → rewrite."""
    from telegram_bot.agents.history_graph.nodes import route_history_grade

    state = {"results_relevant": False, "rewrite_count": 0, "max_rewrite_attempts": 1}
    assert route_history_grade(state) == "rewrite"


def test_route_history_grade_exhausted():
    """Not relevant + rewrites exhausted → summarize (fallback)."""
    from telegram_bot.agents.history_graph.nodes import route_history_grade

    state = {"results_relevant": False, "rewrite_count": 1, "max_rewrite_attempts": 1}
    assert route_history_grade(state) == "summarize"


# --- summarize node ---


async def test_summarize_node_calls_llm(_patch_observe):
    """summarize_node calls LLM with history context and returns summary."""
    from telegram_bot.agents.history_graph.nodes import history_summarize_node

    mock_llm = AsyncMock()
    mock_response = AsyncMock()
    mock_response.choices = [
        AsyncMock(message=AsyncMock(content="Ранее вы спрашивали о ценах в Варне."))
    ]
    mock_llm.chat.completions.create = AsyncMock(return_value=mock_response)

    state = {
        "query": "цены",
        "user_id": 42,
        "results": [
            {
                "query": "цены на квартиры",
                "response": "Средние цены в Варне от 80k EUR",
                "timestamp": "2026-02-13T10:00",
                "score": 0.9,
            },
        ],
        "results_relevant": True,
        "rewrite_count": 0,
        "max_rewrite_attempts": 1,
        "summary": "",
        "latency_stages": {},
    }
    result = await history_summarize_node(state, llm=mock_llm)

    assert "Ранее вы спрашивали" in result["summary"]
    mock_llm.chat.completions.create.assert_called_once()


async def test_summarize_node_empty_results_fallback(_patch_observe):
    """Empty results produce fallback message without LLM call."""
    from telegram_bot.agents.history_graph.nodes import history_summarize_node

    mock_llm = AsyncMock()
    state = {
        "query": "несуществующий",
        "user_id": 42,
        "results": [],
        "results_relevant": False,
        "rewrite_count": 0,
        "max_rewrite_attempts": 1,
        "summary": "",
        "latency_stages": {},
    }
    result = await history_summarize_node(state, llm=mock_llm)

    assert "не найдено" in result["summary"].lower()
    mock_llm.chat.completions.create.assert_not_called()


async def test_summarize_node_llm_failure_returns_raw(_patch_observe):
    """LLM failure falls back to raw formatted results."""
    from telegram_bot.agents.history_graph.nodes import history_summarize_node

    mock_llm = AsyncMock()
    mock_llm.chat.completions.create = AsyncMock(side_effect=RuntimeError("LLM down"))

    state = {
        "query": "цены",
        "user_id": 42,
        "results": [
            {
                "query": "цены",
                "response": "Средние цены...",
                "timestamp": "2026-02-13T10:00",
                "score": 0.9,
            },
        ],
        "results_relevant": True,
        "rewrite_count": 0,
        "max_rewrite_attempts": 1,
        "summary": "",
        "latency_stages": {},
    }
    result = await history_summarize_node(state, llm=mock_llm)

    assert isinstance(result["summary"], str)
    assert len(result["summary"]) > 0
    # Falls back to raw format
    assert "цены" in result["summary"]


# --- Langfuse scores ---


def test_write_history_scores():
    """write_history_scores writes 4 scores with explicit trace_id (#435)."""
    from unittest.mock import MagicMock

    from telegram_bot.agents.history_graph.nodes import write_history_scores

    mock_lf = MagicMock()

    result = {
        "results": [{"score": 0.9}],
        "results_relevant": True,
        "rewrite_count": 1,
        "latency_stages": {"retrieve": 0.1, "grade": 0.01, "summarize": 0.3},
    }
    write_history_scores(mock_lf, result, trace_id="test-trace-id")

    score_names = {c.kwargs["name"] for c in mock_lf.create_score.call_args_list}
    assert "history_results_count" in score_names
    assert "history_relevance" in score_names
    assert "history_rewrite_count" in score_names
    assert "history_latency_ms" in score_names
    # All scores use explicit trace_id
    for call in mock_lf.create_score.call_args_list:
        assert call.kwargs["trace_id"] == "test-trace-id"
