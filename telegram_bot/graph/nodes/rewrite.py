"""rewrite_node — LLM query reformulation for improved retrieval.

Rewrites the user query to improve search relevance.
Increments rewrite_count and resets query_embedding to force re-embedding.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime

from telegram_bot.graph.context import GraphContext
from telegram_bot.observability import get_client, observe
from telegram_bot.services.rag_core import rewrite_query_via_llm


logger = logging.getLogger(__name__)


@observe(name="node-rewrite")
async def rewrite_node(
    state: dict[str, Any],
    runtime: Runtime[GraphContext],
) -> dict[str, Any]:
    """LangGraph node: rewrite the user query for better retrieval.

    Calls LLM to reformulate the query. Increments rewrite_count and
    resets query_embedding to None so cache_check/retrieve will re-embed.

    Args:
        state: RAGState dict
        runtime: LangGraph Runtime with GraphContext (llm)

    Returns:
        State update with rewritten message, incremented rewrite_count,
        reset query_embedding, and latency.
    """
    llm: Any | None = runtime.context.get("llm")
    t0 = time.perf_counter()

    messages = state.get("messages", [])
    original_query = (
        messages[-1].content if hasattr(messages[-1], "content") else messages[-1]["content"]
    )
    rewrite_count = state.get("rewrite_count", 0)

    try:
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig.from_env()
        if llm is None:
            llm = config.create_llm()
        rewritten, effective, rewrite_actual_model = await rewrite_query_via_llm(
            original_query, llm=llm
        )
    except Exception as e:
        logger.exception("rewrite_node: LLM rewrite failed, keeping original query")
        get_client().update_current_span(
            level="ERROR",
            status_message=f"Rewrite LLM failed: {str(e)[:200]}",
        )
        rewritten = original_query
        effective = False
        rewrite_actual_model = "fallback"

    elapsed = time.perf_counter() - t0
    logger.info(
        "rewrite: attempt %d, '%.50s' → '%.50s' (%.3fs)",
        rewrite_count + 1,
        original_query,
        rewritten,
        elapsed,
    )

    return {
        "messages": [HumanMessage(content=rewritten)],
        "rewrite_count": rewrite_count + 1,
        "rewrite_effective": effective,
        "query_embedding": None,
        "sparse_embedding": None,
        "rewrite_provider_model": rewrite_actual_model,
        "llm_call_count": state.get("llm_call_count", 0) + 1,
        "latency_stages": {**state.get("latency_stages", {}), "rewrite": elapsed},
    }
