"""RAG search tool — wraps existing 11-node LangGraph pipeline (#413).

Phase 1: Thin wrapper around build_graph().ainvoke().
Phase 2 (follow-up): Plain async + @observe (no LangGraph dependency).

Dependencies injected via config["configurable"]["bot_context"].
"""

from __future__ import annotations

import logging

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.graph.graph import build_graph
from telegram_bot.graph.state import make_initial_state
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


@tool
@observe(name="tool-rag-search", capture_input=False, capture_output=False)
async def rag_search(
    query: str,
    config: RunnableConfig,
    property_type: str | None = None,
    budget_range: str | None = None,
) -> str:
    """Search real estate knowledge base for properties and information.

    Use this tool when the user asks about the domain topic (e.g., real estate,
    legal documents). Returns relevant information from the document collection.

    Args:
        query: The search query.
        property_type: Optional filter by property type.
        budget_range: Optional filter by budget range.
    """
    ctx = config.get("configurable", {}).get("bot_context")

    lf = get_client()
    lf.update_current_span(input={"query_preview": query[:120]})

    try:
        state = make_initial_state(
            user_id=ctx.telegram_user_id if ctx else 0,
            session_id=ctx.session_id if ctx else "",
            query=query,
        )
        graph = build_graph(
            cache=ctx.cache if ctx else None,
            embeddings=ctx.embeddings if ctx else None,
            sparse_embeddings=ctx.sparse_embeddings if ctx else None,
            qdrant=ctx.qdrant if ctx else None,
            reranker=ctx.reranker if ctx else None,
            llm=ctx.llm if ctx else None,
            content_filter_enabled=ctx.content_filter_enabled if ctx else True,
            guard_mode=ctx.guard_mode if ctx else "hard",
        )
        result = await graph.ainvoke(state)

        response = result.get("response", "") if isinstance(result, dict) else ""
        lf.update_current_span(output={"response_length": len(response)})

        return response or "Ничего не найдено по вашему запросу."
    except Exception:
        logger.exception("RAG pipeline failed")
        lf.update_current_span(level="ERROR", status_message="RAG pipeline failed")
        return "Произошла ошибка при поиске. Попробуйте позже."
