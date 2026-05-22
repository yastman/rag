"""Tests for HistoryState schema (#408 Task 1)."""

from __future__ import annotations


def test_history_state_has_required_fields():
    """HistoryState TypedDict has all required fields."""
    from telegram_bot.agents.history_graph.state import HistoryState

    hints = HistoryState.__annotations__
    assert "query" in hints
    assert "user_id" in hints
    assert "results" in hints
    assert "results_relevant" in hints
    assert "rewrite_count" in hints
    assert "summary" in hints
    assert "latency_stages" in hints


def test_make_history_state_defaults():
    """make_history_state() produces valid initial state."""
    from telegram_bot.agents.history_graph.state import make_history_state

    state = make_history_state(user_id=42, query="цены на квартиры")
    assert state["user_id"] == 42
    assert state["query"] == "цены на квартиры"
    assert state["results"] == []
    assert state["results_relevant"] is False
    assert state["rewrite_count"] == 0
    assert state["summary"] == ""
    assert state["latency_stages"] == {}
