"""grade_node — score-based document relevance grading.

Heuristic: if top document score > threshold, documents are relevant.
LLM-based grading deferred to Phase 5 (agentic).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from telegram_bot.observability import observe


logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 0.3


@observe(name="node-grade")
async def grade_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: grade retrieved documents by relevance.

    Uses score-based heuristic: if the top document score exceeds
    RELEVANCE_THRESHOLD, documents are considered relevant.

    Returns partial state update with documents_relevant and latency.
    """
    t0 = time.perf_counter()

    documents = state.get("documents", [])

    if not documents:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no documents, marking not relevant (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
        }

    top_score = max(doc.get("score", 0) for doc in documents)
    relevant = top_score > RELEVANCE_THRESHOLD

    # Determine skip_rerank from config threshold
    from telegram_bot.graph.config import GraphConfig

    config = GraphConfig.from_env()
    skip_rerank = relevant and top_score >= config.skip_rerank_threshold

    elapsed = time.perf_counter() - t0
    logger.info(
        "grade: top_score=%.3f threshold=%.3f relevant=%s skip_rerank=%s (%d docs, %.3fs)",
        top_score,
        RELEVANCE_THRESHOLD,
        relevant,
        skip_rerank,
        len(documents),
        elapsed,
    )

    return {
        "documents_relevant": relevant,
        "grade_confidence": top_score,
        "skip_rerank": skip_rerank,
        "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
    }
