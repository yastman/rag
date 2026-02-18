"""Supervisor tools with runtime user context (#240).

Each tool reads user_id/session_id from RunnableConfig.configurable
and delegates to existing services (RAG graph, HistoryService).
"""

from __future__ import annotations

import logging
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import get_client, observe


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
    content_filter_enabled: bool = True,
    guard_mode: str = "hard",
    guard_ml_enabled: bool = False,
    llm_guard_client: Any | None = None,
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
            content_filter_enabled=content_filter_enabled,
            guard_mode=guard_mode,
            guard_ml_enabled=guard_ml_enabled,
            llm_guard_client=llm_guard_client,
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


def create_history_search_tool(
    *,
    history_service: Any,
    llm: Any | None = None,
) -> Any:
    """Create history_search tool wrapping the history sub-graph (#408).

    The tool delegates to build_history_graph().ainvoke() which runs a
    4-node pipeline: retrieve → grade → [rewrite] → summarize.
    """
    from telegram_bot.agents.history_graph.graph import build_history_graph
    from telegram_bot.agents.history_graph.nodes import write_history_scores

    graph = build_history_graph(history_service=history_service, llm=llm)

    @tool
    @observe(name="tool-history-search", capture_input=False, capture_output=False)
    async def history_search(query: str, config: RunnableConfig) -> str:
        """Search conversation history for past interactions.

        Use this tool when the user asks about their previous questions,
        past conversations, or wants to find something discussed earlier.
        Returns an LLM-generated summary of relevant past conversations.
        """
        lf = get_client()
        lf.update_current_span(input={"query_preview": query[:120]})

        user_id, _session_id = _get_user_context(config)
        if user_id is None:
            return "Error: user context not available. Cannot search history."

        try:
            from telegram_bot.agents.history_graph.state import make_history_state

            state = make_history_state(user_id=user_id, query=query)
            result = await graph.ainvoke(state)

            if isinstance(result, dict):
                write_history_scores(lf, result)
                summary = result.get("summary", "")
                lf.update_current_span(output={"summary_length": len(summary)})
                return summary or f"По запросу «{query}» ничего не найдено в истории диалогов."
            return f"По запросу «{query}» ничего не найдено в истории диалогов."
        except Exception:
            logger.exception("History search sub-graph failed")
            lf.update_current_span(level="ERROR", status_message="History sub-graph failed")
            return "Произошла ошибка при поиске в истории. Попробуйте позже."

    return history_search


@tool
@observe(name="tool-direct-response")
async def direct_response(message: str) -> str:
    """Respond directly to the user without searching.

    Use this tool for greetings, chitchat, off-topic questions,
    or when you can answer without consulting the knowledge base.
    """
    return message
