"""History search tool — wraps existing history sub-graph (#413).

Phase 1: Delegates to build_history_graph() (existing 4-node pipeline).
Dependencies injected via config["configurable"]["bot_context"].

Semantic caching added in #431/#464:
  1. Embedding cache — get_embedding / store_embedding (7d TTL)
  2. Semantic cache — check_semantic / store_semantic (ENTITY, 1h TTL, threshold=0.10)
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.agents.history_graph.graph import build_history_graph
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


@tool
@observe(name="tool-history-search", capture_input=False, capture_output=False)
async def history_search(
    query: str,
    config: RunnableConfig,
    deal_id: int | None = None,
    scope: str = "all",
) -> str:
    """Search conversation history for past interactions.

    Use this tool when the user asks about their previous questions,
    past conversations, or wants to find something discussed earlier.

    Args:
        query: What to search for in history.
        deal_id: Optional CRM deal ID to scope results.
        scope: 'all' | 'deal' | 'chat' — filter scope.
    """
    ctx = config.get("configurable", {}).get("bot_context")

    lf = get_client()
    lf.update_current_span(input={"query_preview": query[:120], "deal_id": deal_id})

    cache = ctx.cache if ctx else None
    embeddings_svc = ctx.embeddings if ctx else None
    embedding: list[float] | None = None
    history_cache_hit = False

    try:
        # --- Semantic cache check (before graph) ---
        if cache is not None and embeddings_svc is not None:
            # Step 1: Get or compute dense embedding
            embedding = await cache.get_embedding(query)
            if embedding is None:
                try:
                    _has_hybrid = callable(
                        getattr(embeddings_svc, "aembed_hybrid", None)
                    ) and asyncio.iscoroutinefunction(embeddings_svc.aembed_hybrid)
                    if _has_hybrid:
                        embedding, _ = await embeddings_svc.aembed_hybrid(query)
                    else:
                        embedding = await embeddings_svc.aembed_query(query)
                    await cache.store_embedding(query, embedding)
                except Exception:
                    logger.warning("History cache: embedding failed, skipping cache check")
                    embedding = None

            # Step 2: Check semantic cache (ENTITY type — history queries are specific)
            if embedding is not None:
                cached_summary = await cache.check_semantic(
                    query, vector=embedding, query_type="ENTITY"
                )
                if cached_summary:
                    history_cache_hit = True
                    logger.info("History semantic cache HIT for query: %.60s", query)
                    from telegram_bot.agents.history_graph.nodes import write_history_scores

                    write_history_scores(
                        lf,
                        {
                            "results": [],
                            "results_relevant": True,
                            "rewrite_count": 0,
                            "latency_stages": {},
                            "history_cache_hit": True,
                        },
                        trace_id=lf.get_current_trace_id() or "",
                    )
                    lf.update_current_span(
                        output={
                            "summary_length": len(cached_summary),
                            "history_cache_hit": True,
                        }
                    )
                    return cached_summary

        # --- Cache miss: run history sub-graph ---
        graph = build_history_graph(
            history_service=ctx.history_service if ctx else None,
            llm=ctx.llm if ctx else None,
            guard_mode=ctx.guard_mode if ctx else "hard",
            content_filter_enabled=ctx.content_filter_enabled if ctx else True,
        )
        state: dict[str, Any] = {
            "query": query,
            "user_id": ctx.telegram_user_id if ctx else 0,
            "results": [],
            "results_relevant": False,
            "rewrite_count": 0,
            "max_rewrite_attempts": 2,
            "summary": "",
        }
        result = await graph.ainvoke(state)

        if isinstance(result, dict):
            from telegram_bot.agents.history_graph.nodes import write_history_scores

            result["history_cache_hit"] = history_cache_hit
            write_history_scores(lf, result, trace_id=lf.get_current_trace_id() or "")
            summary = result.get("summary", "")

            # Step 3: Store summary in semantic cache for future hits
            if cache is not None and embedding is not None and summary:
                await cache.store_semantic(query, summary, vector=embedding, query_type="ENTITY")

            lf.update_current_span(
                output={"summary_length": len(summary), "history_cache_hit": False}
            )
            return summary or f"По запросу «{query}» ничего не найдено в истории диалогов."
        return f"По запросу «{query}» ничего не найдено в истории диалогов."
    except Exception:
        logger.exception("History search failed")
        lf.update_current_span(level="ERROR", status_message="History search failed")
        return "Произошла ошибка при поиске в истории. Попробуйте позже."
