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
