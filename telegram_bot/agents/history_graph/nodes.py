"""History sub-graph nodes — retrieve, grade, rewrite, summarize (#408).

Each node follows the LangGraph pattern: async function(state, **deps) → partial state update.
All nodes decorated with @observe() for Langfuse tracing.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

# --- Retrieve ---

_HISTORY_RETRIEVE_LIMIT = 10


@observe(name="history-retrieve", capture_input=False, capture_output=False)
async def history_retrieve_node(
    state: dict[str, Any],
    *,
    history_service: Any,
) -> dict[str, Any]:
    """Retrieve conversation history via semantic search.

    Calls HistoryService.search_user_history() with user isolation.
    """
    t0 = time.perf_counter()
    query = state["query"]
    user_id = state["user_id"]

    lf = get_client()
    lf.update_current_span(input={"query_preview": query[:120], "user_id": user_id})

    try:
        results = await history_service.search_user_history(
            user_id=user_id,
            query=query,
            limit=_HISTORY_RETRIEVE_LIMIT,
        )
    except Exception as e:
        logger.exception("history_retrieve_node: search failed")
        lf.update_current_span(
            level="ERROR", status_message=f"History search failed: {str(e)[:200]}"
        )
        results = []

    elapsed = time.perf_counter() - t0
    logger.info("history_retrieve: %d results for user=%s (%.3fs)", len(results), user_id, elapsed)

    lf.update_current_span(
        output={"results_count": len(results), "duration_ms": round(elapsed * 1000, 1)}
    )

    return {
        "results": results,
        "latency_stages": {**state.get("latency_stages", {}), "retrieve": elapsed},
    }


# --- Grade ---

_HISTORY_RELEVANCE_THRESHOLD = 0.7


@observe(name="history-grade")
async def history_grade_node(state: dict[str, Any]) -> dict[str, Any]:
    """Grade retrieved history results by relevance score.

    Filters out results below threshold and marks overall relevance.
    """
    t0 = time.perf_counter()
    results = state.get("results", [])

    if not results:
        elapsed = time.perf_counter() - t0
        return {
            "results_relevant": False,
            "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
        }

    relevant = [r for r in results if r.get("score", 0) >= _HISTORY_RELEVANCE_THRESHOLD]
    is_relevant = len(relevant) > 0

    elapsed = time.perf_counter() - t0
    logger.info(
        "history_grade: %d/%d relevant (threshold=%.2f, %.3fs)",
        len(relevant),
        len(results),
        _HISTORY_RELEVANCE_THRESHOLD,
        elapsed,
    )

    return {
        "results": relevant or results[:3],  # fallback: top-3 if none pass
        "results_relevant": is_relevant,
        "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
    }
