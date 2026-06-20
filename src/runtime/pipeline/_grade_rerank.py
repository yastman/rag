# SPDX-License-Identifier: MIT
"""Grade and rerank pipeline stages."""

from __future__ import annotations

import logging
import time
from typing import Any

from src.observability import get_client, observe
from src.retrieval.topic_classifier import detect_score_gap
from src.runtime.services.metrics import record_pipeline_event
from src.runtime.services.rag_core import perform_rerank


logger = logging.getLogger(__name__)

# top_k=7 for reranking. Standard in literature; balances latency vs recall for
# reranking candidate pool. 3 was too restrictive — comprehensive queries
# (e.g. list all ВНЖ types) were losing chunks.
_DEFAULT_RERANK_TOP_K = 7


def _graph_config_from_env() -> Any:
    from src.runtime.graph.config import GraphConfig

    return GraphConfig.from_env()


# ---------------------------------------------------------------------------
# Step 3: Grade documents
# ---------------------------------------------------------------------------


@observe(name="grade-documents", as_type="evaluator")
async def _grade_documents(
    documents: list[dict[str, Any]],
    prev_confidence: float,
    *,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Grade retrieved documents by relevance using score-based heuristic.

    Returns dict with documents_relevant, grade_confidence, skip_rerank, score_improved.
    """
    t0 = time.perf_counter()

    if not documents:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no documents, marking not relevant (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "grade_confidence": 0.0,
            "skip_rerank": False,
            "score_improved": False,
            "latency_stages": {**latency_stages, "grade": elapsed},
        }

    scores = [doc.get("score", 0) for doc in documents if isinstance(doc, dict)]
    if not scores:
        elapsed = time.perf_counter() - t0
        logger.info("grade: no valid scored documents (%.3fs)", elapsed)
        return {
            "documents_relevant": False,
            "grade_confidence": 0.0,
            "skip_rerank": False,
            "score_improved": False,
            "latency_stages": {**latency_stages, "grade": elapsed},
        }

    top_score = max(scores)
    score_gap = detect_score_gap(sorted(scores, reverse=True))

    config = _graph_config_from_env()
    relevant = top_score > config.relevance_threshold_rrf
    skip_rerank = relevant and top_score >= config.skip_rerank_threshold

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
        config.relevance_threshold_rrf,
        relevant,
        skip_rerank,
        len(documents),
        elapsed,
    )
    record_pipeline_event("score_gap_confident", 1 if score_gap["confident"] else 0)

    return {
        "documents_relevant": relevant,
        "grade_confidence": top_score,
        "skip_rerank": skip_rerank,
        "score_improved": score_improved,
        "score_gap_confident": score_gap["confident"],
        "latency_stages": {**latency_stages, "grade": elapsed},
    }


# ---------------------------------------------------------------------------
# Step 4: Rerank
# ---------------------------------------------------------------------------


@observe(name="rerank")
async def _rerank(
    query: str,
    documents: list[dict[str, Any]],
    *,
    cache: Any | None = None,
    reranker: Any | None = None,
    top_k: int = _DEFAULT_RERANK_TOP_K,
    latency_stages: dict[str, float],
) -> dict[str, Any]:
    """Rerank documents using ColBERT or score-based fallback.

    Returns dict with documents, rerank_applied, rerank_cache_hit, and latency.
    """
    t0 = time.perf_counter()

    if not documents:
        elapsed = time.perf_counter() - t0
        return {
            "documents": [],
            "rerank_applied": False,
            "rerank_cache_hit": False,
            "latency_stages": {**latency_stages, "rerank": elapsed},
        }

    try:
        reranked_docs, rerank_applied, rerank_cache_hit = await perform_rerank(
            query, documents, cache=cache, reranker=reranker, top_k=top_k
        )
        if not rerank_applied:
            # No reranker path: sort and trim here
            reranked_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[:top_k]
    except Exception as e:
        logger.exception("rerank: ColBERT failed, falling back to score sort")
        get_client().update_current_span(
            level="ERROR",
            status_message=f"ColBERT rerank failed: {str(e)[:200]}",
        )
        reranked_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[:top_k]
        rerank_applied = False
        rerank_cache_hit = False

    if len(reranked_docs) >= 3:
        top_scores = [float(doc.get("score", 0.0)) for doc in reranked_docs[:3]]
        lead_gap = detect_score_gap(top_scores[:2])
        tail_gap = detect_score_gap(top_scores[1:3])
        if not bool(lead_gap["confident"]) and bool(tail_gap["confident"]):
            reranked_docs = reranked_docs[:2]

    elapsed = time.perf_counter() - t0
    logger.info(
        "rerank: %d → %d docs, applied=%s cache_hit=%s (%.3fs)",
        len(documents),
        len(reranked_docs),
        rerank_applied,
        rerank_cache_hit,
        elapsed,
    )
    return {
        "documents": reranked_docs,
        "rerank_applied": rerank_applied,
        "rerank_cache_hit": rerank_cache_hit,
        "latency_stages": {**latency_stages, "rerank": elapsed},
    }
