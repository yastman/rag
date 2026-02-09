"""rewrite_node — LLM query reformulation for improved retrieval.

Rewrites the user query to improve search relevance.
Increments rewrite_count and resets query_embedding to force re-embedding.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage


logger = logging.getLogger(__name__)


def _get_llm() -> Any:
    """Create LLM instance from GraphConfig."""
    from telegram_bot.graph.config import GraphConfig

    return GraphConfig.from_env().create_llm()


_REWRITE_PROMPT = (
    "Ты — помощник по поиску недвижимости. "
    "Пользователь задал вопрос, но результаты поиска оказались нерелевантными.\n\n"
    "Переформулируй запрос так, чтобы он лучше подходил для поиска по базе недвижимости.\n"
    "Верни ТОЛЬКО переформулированный запрос, без пояснений.\n\n"
    "Оригинальный запрос: {query}"
)


async def rewrite_node(
    state: dict[str, Any],
    *,
    llm: Any | None = None,
) -> dict[str, Any]:
    """LangGraph node: rewrite the user query for better retrieval.

    Calls LLM to reformulate the query. Increments rewrite_count and
    resets query_embedding to None so cache_check/retrieve will re-embed.

    Args:
        state: RAGState dict
        llm: Optional LLM instance (uses GraphConfig default if None)

    Returns:
        State update with rewritten message, incremented rewrite_count,
        reset query_embedding, and latency.
    """
    t0 = time.perf_counter()

    messages = state.get("messages", [])
    original_query = (
        messages[-1].content if hasattr(messages[-1], "content") else messages[-1]["content"]
    )
    rewrite_count = state.get("rewrite_count", 0)

    try:
        if llm is None:
            llm = _get_llm()

        prompt = _REWRITE_PROMPT.format(query=original_query)
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        rewritten = response.content if hasattr(response, "content") else str(response)
        rewritten = rewritten.strip()

        if not rewritten:
            rewritten = original_query
    except Exception:
        logger.exception("rewrite_node: LLM rewrite failed, keeping original query")
        rewritten = original_query

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
        "query_embedding": None,
        "sparse_embedding": None,
        "latency_stages": {**state.get("latency_stages", {}), "rewrite": elapsed},
    }
