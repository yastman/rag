"""rerank_node — optional ColBERT reranking of retrieved documents.

If reranker is provided, uses ColBERT MaxSim scoring.
Otherwise, falls back to score-based sort with top-5 selection.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

_DEFAULT_TOP_K = 5


@observe(name="node-rerank")
async def rerank_node(
    state: dict[str, Any],
    *,
    reranker: Any | None = None,
    top_k: int = _DEFAULT_TOP_K,
) -> dict[str, Any]:
    """LangGraph node: rerank documents using ColBERT or score-based fallback.

    Args:
        state: RAGState dict (needs documents, messages)
        reranker: Optional ColbertRerankerService instance
        top_k: Number of top results to keep

    Returns:
        State update with reranked documents, rerank_applied flag, latency.
    """
    t0 = time.perf_counter()

    documents = state.get("documents", [])
    llm_call_count = state.get("llm_call_count", 0) + 1

    if not documents:
        elapsed = time.perf_counter() - t0
        return {
            "documents": [],
            "rerank_applied": False,
            "llm_call_count": llm_call_count,
            "latency_stages": {**state.get("latency_stages", {}), "rerank": elapsed},
        }

    query = (
        state["messages"][-1].content
        if hasattr(state["messages"][-1], "content")
        else state["messages"][-1]["content"]
    )

    if reranker is not None:
        try:
            doc_texts = [doc.get("text", "") for doc in documents]
            rerank_results = await reranker.rerank(query=query, documents=doc_texts, top_k=top_k)

            reranked: list[dict[str, Any]] = []
            for rr in rerank_results:
                idx = rr["index"]
                if idx < len(documents):
                    doc = {**documents[idx], "score": rr["score"]}
                    reranked.append(doc)

            elapsed = time.perf_counter() - t0
            logger.info(
                "rerank: ColBERT reranked %d → %d docs (%.3fs)",
                len(documents),
                len(reranked),
                elapsed,
            )
            return {
                "documents": reranked,
                "rerank_applied": True,
                "llm_call_count": llm_call_count,
                "latency_stages": {**state.get("latency_stages", {}), "rerank": elapsed},
            }
        except Exception as e:
            logger.exception("rerank: ColBERT failed, falling back to score sort")
            get_client().update_current_span(
                level="ERROR",
                status_message=f"ColBERT rerank failed: {str(e)[:200]}",
            )

    # Fallback: sort by existing score, take top-k
    sorted_docs = sorted(documents, key=lambda d: d.get("score", 0), reverse=True)[:top_k]

    elapsed = time.perf_counter() - t0
    logger.info(
        "rerank: score-based sort %d → %d docs (%.3fs)",
        len(documents),
        len(sorted_docs),
        elapsed,
    )
    return {
        "documents": sorted_docs,
        "rerank_applied": False,
        "llm_call_count": llm_call_count,
        "latency_stages": {**state.get("latency_stages", {}), "rerank": elapsed},
    }
