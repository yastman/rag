"""RAG agent — wraps existing RAG graph as a supervisor tool (#240 Task 3).

Thin wrapper around build_graph().ainvoke() that exposes the existing
10-node RAG pipeline as a LangChain tool for the supervisor.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.agents.tools import _get_user_context
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


def create_rag_agent(
    *,
    cache: Any,
    embeddings: Any,
    sparse_embeddings: Any,
    qdrant: Any,
    reranker: Any | None = None,
    llm: Any | None = None,
) -> Any:
    """Create RAG agent tool wrapping the existing LangGraph pipeline.

    The tool delegates to `build_graph().ainvoke()` with all injected services.
    Error handling ensures the supervisor gets a controlled string response
    even if the RAG pipeline fails.
    """

    @tool
    @observe(name="tool-rag-search", capture_input=False, capture_output=False)
    async def rag_search(query: str, config: RunnableConfig) -> str:
        """Search the knowledge base for domain-specific information.

        Use this tool when the user asks about the domain topic (e.g., real estate,
        legal documents). Returns relevant information from the document collection.
        """
        from telegram_bot.graph.graph import build_graph
        from telegram_bot.graph.state import make_initial_state

        lf = get_client()
        lf.update_current_span(input={"query_preview": query[:120]})

        user_id, session_id = _get_user_context(config)
        if user_id is None:
            return "Error: user context not available. Cannot perform search."

        try:
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
                lf.update_current_span(output={"response_length": len(str(response))})
                return cast(str, response)
            return "No response generated."
        except Exception:
            logger.exception("RAG agent graph invocation failed")
            lf.update_current_span(level="ERROR", status_message="RAG graph invocation failed")
            return "Произошла ошибка при поиске. Попробуйте позже."

    return rag_search
