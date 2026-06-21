"""History search tool — semantic-cached history lookup (#413, #2945).

history_graph was removed in #2843. This module retains the cache layer and
tool contract so the agent can still call history_search without errors.

Cache key fix (#2945): deal_id is now included in filter_signature so that
different deals/contexts never collide on the same cached entry.
"""

from __future__ import annotations

import logging

from telegram_bot.agents.context import get_bot_context
from telegram_bot.agents.tooling import RunnableConfig, tool
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


@tool
@observe(name="tool-history-search", capture_input=False, capture_output=False, as_type="tool")
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
    ctx = get_bot_context(None, config)
    lf = get_client()
    if lf is not None:
        lf.update_current_span(input={"query_preview": query[:120], "deal_id": deal_id})

    cache = ctx.cache if ctx else None
    embeddings_svc = ctx.embeddings if ctx else None
    user_id_val = ctx.telegram_user_id if ctx else None

    # Include deal_id in filter_signature so different deals never share a cache entry (#2945)
    filter_signature = f"deal:{deal_id}" if deal_id is not None else "deal:none"

    if cache is not None and embeddings_svc is not None:
        embedding = await cache.get_embedding(query)
        if embedding is None:
            try:
                embedding = await embeddings_svc.aembed_query(query)
                await cache.store_embedding(query, embedding)
            except Exception:
                logger.warning("History cache: embedding failed, skipping cache check")
                embedding = None

        if embedding is not None:
            cached = await cache.check_semantic(
                query,
                vector=embedding,
                query_type="ENTITY",
                user_id=user_id_val,
                cache_scope="history",
                filter_signature=filter_signature,
            )
            if cached:
                if lf is not None:
                    lf.update_current_span(output={"history_cache_hit": True})
                return str(cached)

    # ponytail: history_graph removed in #2843; restore sub-graph when history
    # retrieval is re-implemented (track under a new issue).
    if lf is not None:
        lf.update_current_span(output={"history_cache_hit": False, "graph_unavailable": True})
    return f"По запросу «{query}» ничего не найдено в истории диалогов."
