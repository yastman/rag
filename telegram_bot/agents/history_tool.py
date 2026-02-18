"""History search tool — wraps existing history sub-graph (#413).

Phase 1: Delegates to build_history_graph() (existing 4-node pipeline).
Dependencies injected via config["configurable"]["bot_context"].
"""

from __future__ import annotations

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

    try:
        graph = build_history_graph(
            history_service=ctx.history_service if ctx else None,
            llm=ctx.llm if ctx else None,
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

            write_history_scores(lf, result)
            summary = result.get("summary", "")
            lf.update_current_span(output={"summary_length": len(summary)})
            return summary or f"По запросу «{query}» ничего не найдено в истории диалогов."
        return f"По запросу «{query}» ничего не найдено в истории диалогов."
    except Exception:
        logger.exception("History search failed")
        lf.update_current_span(level="ERROR", status_message="History search failed")
        return "Произошла ошибка при поиске в истории. Попробуйте позже."
