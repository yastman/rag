"""History agent — conversation history search tool (#240 Task 4).

Uses existing HistoryService (Qdrant + BGE-M3) for semantic search
over user's past conversations.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.agents.tools import _get_user_context
from telegram_bot.observability import observe


logger = logging.getLogger(__name__)


def create_history_agent(*, history_service: Any) -> Any:
    """Create history_search tool wrapping HistoryService.

    The tool delegates to search_user_history() and formats results
    as a concise text response (no additional LLM call — MVP).
    """

    @tool
    @observe(name="tool-history-search")
    async def history_search(query: str, config: RunnableConfig) -> str:
        """Search conversation history for past interactions.

        Use this tool when the user asks about their previous questions,
        past conversations, or wants to find something discussed earlier.
        """
        user_id, _session_id = _get_user_context(config)
        if user_id is None:
            return "Error: user context not available. Cannot search history."

        try:
            results = await history_service.search_user_history(
                user_id=user_id,
                query=query,
                limit=5,
            )
        except Exception:
            logger.exception("History search failed")
            return "Произошла ошибка при поиске в истории. Попробуйте позже."

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
