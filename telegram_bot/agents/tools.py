"""Supervisor tools with runtime user context (#240).

Each tool reads user_id/session_id from RunnableConfig.configurable
and delegates to existing services (RAG graph, HistoryService).
"""

from __future__ import annotations

import logging
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool


logger = logging.getLogger(__name__)


def _get_user_context(config: RunnableConfig) -> tuple[int | None, str | None]:
    """Extract user_id and session_id from RunnableConfig."""
    configurable = (config or {}).get("configurable", {})
    user_id = configurable.get("user_id")
    session_id = configurable.get("session_id")
    return user_id, session_id


def create_rag_search_tool(
    *,
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    reranker: Any | None = None,
    llm: Any | None = None,
) -> Any:
    """Create rag_search tool with injected services."""

    @tool
    async def rag_search(query: str, config: RunnableConfig) -> str:
        """Search the knowledge base for domain-specific information.

        Use this tool when the user asks about the domain topic (e.g., real estate,
        legal documents). Returns relevant information from the document collection.
        """
        from telegram_bot.graph.graph import build_graph
        from telegram_bot.graph.state import make_initial_state

        user_id, session_id = _get_user_context(config)
        if user_id is None:
            return "Error: user context not available. Cannot perform search."

        graph = build_graph(
            cache=cache,
            embeddings=embeddings,
            sparse_embeddings=sparse_embeddings,
            qdrant=qdrant,
            reranker=reranker,
            llm=llm,
        )
        state = make_initial_state(
            user_id=user_id,
            session_id=session_id or "",
            query=query,
        )
        result = await graph.ainvoke(state)
        if isinstance(result, dict):
            response = result.get("response", "No response generated.")
            return cast(str, response)
        return "No response generated."

    return rag_search


def create_history_search_tool(*, history_service: Any) -> Any:
    """Create history_search tool with injected HistoryService."""

    @tool
    async def history_search(query: str, config: RunnableConfig) -> str:
        """Search conversation history for past interactions.

        Use this tool when the user asks about their previous questions,
        past conversations, or wants to find something discussed earlier.
        """
        user_id, _session_id = _get_user_context(config)
        if user_id is None:
            return "Error: user context not available. Cannot search history."

        results = await history_service.search_user_history(
            user_id=user_id,
            query=query,
            limit=5,
        )

        if not results:
            return f"По запросу «{query}» ничего не найдено в истории диалогов."

        lines = []
        for i, r in enumerate(results, 1):
            ts = r.get("timestamp", "")[:16].replace("T", " ")
            lines.append(f"{i}. [{ts}] Q: {r['query']}")
            resp_preview = r["response"][:150]
            if len(r["response"]) > 150:
                resp_preview += "..."
            lines.append(f"   A: {resp_preview}")

        return "\n".join(lines)

    return history_search


@tool
async def direct_response(message: str) -> str:
    """Respond directly to the user without searching.

    Use this tool for greetings, chitchat, off-topic questions,
    or when you can answer without consulting the knowledge base.
    """
    return message
