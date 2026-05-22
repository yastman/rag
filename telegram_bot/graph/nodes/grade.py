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


@observe(name="node-grade")
async def grade_node(state: dict[str, Any]) -> dict[str, Any]:
    """LangGraph node: grade retrieved documents by relevance.

    Uses score-based heuristic: if the top document score exceeds
    RELEVANCE_THRESHOLD, documents are considered relevant.

    Returns partial state update with documents_relevant and latency.
    """
    t0 = time.perf_counter()

    documents = state.get("documents", [])
    prev_confidence = state.get("grade_confidence", 0.0)

    if not documents:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no documents, marking not relevant (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "grade_confidence": 0.0,
            "skip_rerank": False,
            "score_improved": False,
            "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
        }

    # Defensive normalization: documents can include non-dict placeholders.
    scores = [doc.get("score", 0) for doc in documents if isinstance(doc, dict)]
    if not scores:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no valid scored documents, marking not relevant (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "grade_confidence": 0.0,
            "skip_rerank": False,
            "score_improved": False,
            "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
        }

    top_score = max(scores)

    # RRF scores = 1/(k+rank), k=60 → rank 1 = ~0.016, rank 10 = ~0.014
    # Threshold must be below typical top-1 RRF score
    from telegram_bot.graph.config import GraphConfig

    config = GraphConfig.from_env()
    relevance_threshold = config.relevance_threshold_rrf
    relevant = top_score > relevance_threshold

    # Early termination: skip rerank when confidence is high enough
    skip_rerank = relevant and top_score >= config.skip_rerank_threshold

    # Score improvement check for rewrite guard
    delta = top_score - prev_confidence
    score_improved = delta >= config.score_improvement_delta or prev_confidence == 0.0

    elapsed = time.perf_counter() - t0
    logger.info(
        "grade: top_score=%.4f prev=%.4f delta=%.4f improved=%s "
        "threshold=%.3f relevant=%s skip_rerank=%s (%d docs, %.3fs)",
        top_score,
        prev_confidence,
        delta,
        score_improved,
        relevance_threshold,
        relevant,
        skip_rerank,
        len(documents),
        elapsed,
    )

    return {
        "documents_relevant": relevant,
        "grade_confidence": top_score,
        "skip_rerank": skip_rerank,
        "score_improved": score_improved,
        "latency_stages": {**state.get("latency_stages", {}), "grade": elapsed},
    }
