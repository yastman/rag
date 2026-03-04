"""rerank_node — optional ColBERT reranking of retrieved documents.

If reranker is provided, uses ColBERT MaxSim scoring.
Otherwise, falls back to score-based sort with top-5 selection.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langgraph.runtime import Runtime

from telegram_bot.graph.context import GraphContext
from telegram_bot.observability import get_client, observe
from telegram_bot.services.metrics import PipelineMetrics
from telegram_bot.services.rag_core import perform_rerank


logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 5


@observe(name="node-rerank")
async def rerank_node(
    state: dict[str, Any],
    runtime: Runtime[GraphContext],
    top_k: int = _DEFAULT_TOP_K,
) -> dict[str, Any]:
    """LangGraph node: rerank documents using ColBERT or score-based fallback.

    Args:
        state: RAGState dict (needs documents, messages)
        runtime: LangGraph Runtime with GraphContext (cache, reranker)
        top_k: Number of top results to keep

    Returns:
        State update with reranked documents, rerank_applied, rerank_cache_hit, latency.
    """
    cache: Any | None = runtime.context.get("cache")
    reranker: Any | None = runtime.context.get("reranker")
    t0 = time.perf_counter()

    documents = state.get("documents", [])
    llm_call_count = state.get("llm_call_count", 0) + 1

    if not documents:
        elapsed = time.perf_counter() - t0
        PipelineMetrics.get().record("rerank", elapsed * 1000)
        return {
            "documents": [],
            "rerank_applied": False,
            "rerank_cache_hit": False,
            "llm_call_count": llm_call_count,
            "latency_stages": {**state.get("latency_stages", {}), "rerank": elapsed},
        }

    query = (
        state["messages"][-1].content
        if hasattr(state["messages"][-1], "content")
        else state["messages"][-1]["content"]
    )

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

    elapsed = time.perf_counter() - t0
    PipelineMetrics.get().record("rerank", elapsed * 1000)
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
        "llm_call_count": llm_call_count,
        "latency_stages": {**state.get("latency_stages", {}), "rerank": elapsed},
    }
