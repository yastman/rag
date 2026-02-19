"""RAG search tool — wraps async rag_pipeline (#442).

Pipeline returns CONTEXT (documents, scores, latency_stages).
Agent generates ANSWER from the returned context string.

Dependencies injected via config["configurable"]["bot_context"].
"""

from __future__ import annotations

import logging
import time

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.agents.rag_pipeline import rag_pipeline
from telegram_bot.observability import get_client, observe
from telegram_bot.scoring import write_langfuse_scores


logger = logging.getLogger(__name__)


def _format_context(result: dict) -> str:
    """Format pipeline result as context string for agent LLM."""
    if result.get("cache_hit") and result.get("response"):
        return result["response"]

    documents = result.get("documents", [])
    if not documents:
        return "Ничего не найдено по вашему запросу."

    parts: list[str] = []
    for i, doc in enumerate(documents, 1):
        if not isinstance(doc, dict):
            continue
        text = doc.get("text", "")
        score = doc.get("score", 0)
        meta = doc.get("metadata", {})
        source = meta.get("source", meta.get("title", ""))
        header = f"[{i}] (score: {score:.4f})"
        if source:
            header += f" — {source}"
        parts.append(f"{header}\n{text}")

    return "\n\n".join(parts) if parts else "Ничего не найдено по вашему запросу."


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
    configurable = config.get("configurable", {})
    ctx = configurable.get("bot_context")

    lf = get_client()
    lf.update_current_span(input={"query_preview": query[:120]})

    try:
        invoke_start = time.perf_counter()
        result = await rag_pipeline(
            query,
            user_id=ctx.telegram_user_id if ctx else 0,
            session_id=ctx.session_id if ctx else "",
            cache=ctx.cache if ctx else None,
            embeddings=ctx.embeddings if ctx else None,
            sparse_embeddings=ctx.sparse_embeddings if ctx else None,
            qdrant=ctx.qdrant if ctx else None,
            reranker=ctx.reranker if ctx else None,
            llm=ctx.llm if ctx else None,
        )
        pipeline_wall_ms = (time.perf_counter() - invoke_start) * 1000

        result["pipeline_wall_ms"] = pipeline_wall_ms
        summarize_s = result.get("latency_stages", {}).get("summarize", 0)
        result["user_perceived_wall_ms"] = pipeline_wall_ms - (summarize_s * 1000)

        # Observability must stay fail-soft: scoring errors must not break user response.
        try:
            write_langfuse_scores(lf, result)
        except Exception:
            logger.warning("Failed to write Langfuse scores in rag_search", exc_info=True)

        # Store full result for caller via side-channel (#426)
        result_store = configurable.get("rag_result_store")
        if isinstance(result_store, dict):
            result_store.update(result)

        context = _format_context(result)
        lf.update_current_span(output={"response_length": len(context)})
        return context

    except Exception:
        logger.exception("RAG pipeline failed")
        lf.update_current_span(level="ERROR", status_message="RAG pipeline failed")
        return "Произошла ошибка при поиске. Попробуйте позже."
