"""rewrite_node — LLM query reformulation for improved retrieval.

Rewrites the user query to improve search relevance.
Increments rewrite_count and resets query_embedding to force re-embedding.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain_core.messages import HumanMessage

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


_REWRITE_PROMPT = (
    "Ты — помощник по поиску недвижимости. "
    "Пользователь задал вопрос, но результаты поиска оказались нерелевантными.\n\n"
    "Переформулируй запрос так, чтобы он лучше подходил для поиска по базе недвижимости.\n"
    "Верни ТОЛЬКО переформулированный запрос, без пояснений.\n\n"
    "Оригинальный запрос: {query}"
)


@observe(name="node-rewrite")
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
        from telegram_bot.graph.config import GraphConfig

        config = GraphConfig.from_env()
        if llm is None:
            llm = config.create_llm()

        prompt = _REWRITE_PROMPT.format(query=original_query)
        response = await llm.chat.completions.create(
            model=config.rewrite_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=config.rewrite_max_tokens,
            name="rewrite-query",  # type: ignore[call-overload]  # langfuse kwarg
        )
        rewritten = (response.choices[0].message.content or "").strip()
        rewrite_actual_model = (
            getattr(response, "model", config.rewrite_model) or config.rewrite_model
        )

        if not rewritten or rewritten == original_query:
            rewritten = original_query
            effective = False
        else:
            effective = True
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
