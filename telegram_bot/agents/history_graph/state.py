"""HistoryState schema for the history search sub-graph (#408).

Minimal state for retrieve → grade → rewrite → summarize pipeline.
"""

from __future__ import annotations

from typing import Any, TypedDict


class HistoryState(TypedDict):
    """State for the history search sub-graph.

    Fields:
        query: Current search query (may be rewritten).
        user_id: Telegram user ID for isolation.
        results: Retrieved history items from HistoryService.
        results_relevant: Whether retrieved results pass relevance threshold.
        rewrite_count: Number of query rewrites performed.
        max_rewrite_attempts: Cap on rewrite iterations.
        summary: LLM-generated summary of relevant history.
        latency_stages: Per-node timing breakdown (seconds).
    """

    query: str
    user_id: int
    results: list[dict[str, Any]]
    results_relevant: bool
    rewrite_count: int
    max_rewrite_attempts: int
    summary: str
    latency_stages: dict[str, float]


def make_history_state(
    *,
    user_id: int,
    query: str,
    max_rewrite_attempts: int = 1,
) -> dict[str, Any]:
    """Create initial state for a history sub-graph invocation."""
    return {
        "query": query,
        "user_id": user_id,
        "results": [],
        "results_relevant": False,
        "rewrite_count": 0,
        "max_rewrite_attempts": max_rewrite_attempts,
        "summary": "",
        "latency_stages": {},
    }
