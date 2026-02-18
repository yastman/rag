"""Supervisor tools with runtime user context (#240).

Each tool reads user_id/session_id from RunnableConfig.configurable
and delegates to existing services (RAG graph, HistoryService).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any, cast

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import observe


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
        item_no = 0
        for r in results:
            q = r.get("query")
            resp = r.get("response")
            if not isinstance(q, str) or not isinstance(resp, str):
                continue

            item_no += 1
            ts = str(r.get("timestamp", ""))[:16].replace("T", " ")
            lines.append(f"{item_no}. [{ts}] Q: {q}")
            resp_preview = resp[:150]
            if len(resp) > 150:
                resp_preview += "..."
            lines.append(f"   A: {resp_preview}")

        if not lines:
            return f"По запросу «{query}» ничего не найдено в истории диалогов."

        return "\n".join(lines)

    return history_search


def build_tools_for_role(
    *, role: str, base_tools: list[Any], manager_tools: Iterable[Any]
) -> list[Any]:
    """Select tools based on user role (#388)."""
    tools = list(base_tools)
    if role == "manager":
        tools.extend(list(manager_tools))
    return tools


def create_crm_score_sync_tool(
    *,
    scoring_store: Any,
    kommo_client: Any,
    score_field_id: int,
    band_field_id: int,
) -> Any:
    """Create crm_sync_lead_score tool for supervisor (#384)."""

    @tool
    @observe(name="tool-crm-sync-lead-score")
    async def crm_sync_lead_score(query: str, config: RunnableConfig) -> str:
        """Sync pending lead scores to Kommo CRM.

        Use this tool to push scored leads to the CRM system.
        Handles retries and idempotency automatically.
        """
        user_id, session_id = _get_user_context(config)
        pending = await scoring_store.list_pending_sync(limit=20)
        synced = 0
        failed = 0
        skipped = 0

        for rec in pending:
            if rec.kommo_lead_id is None:
                skipped += 1
                continue
            key = f"lead-score:{rec.lead_id}:{rec.session_id}:{rec.score_value}"
            payload = {
                "custom_fields_values": [
                    {"field_id": score_field_id, "values": [{"value": rec.score_value}]},
                    {"field_id": band_field_id, "values": [{"value": rec.score_band}]},
                ]
            }
            try:
                await kommo_client.update_lead_score(
                    lead_id=rec.kommo_lead_id,
                    payload=payload,
                    idempotency_key=key,
                )
                await scoring_store.mark_synced(lead_id=rec.lead_id)
                synced += 1
            except Exception:
                logger.exception("CRM score sync failed for lead %s", rec.lead_id)
                await scoring_store.mark_failed(lead_id=rec.lead_id, error="kommo_error")
                failed += 1

        return (
            f"CRM score sync completed: synced {synced}, failed {failed}, "
            f"skipped {skipped} (user {user_id}, session {session_id})"
        )

    return crm_sync_lead_score


def create_manager_nurturing_tools(*, analytics_service: Any, nurturing_service: Any) -> list[Any]:
    """Create manager-only nurturing + analytics tools (#390)."""

    @tool
    async def manager_get_funnel_analytics(query: str, config: RunnableConfig) -> str:
        """Get funnel conversion analytics for manager review.

        Returns the latest daily funnel metrics including conversion rates,
        dropoff counts, and stage-level performance data.
        """
        role = (config or {}).get("configurable", {}).get("role", "client")
        if role not in {"manager", "admin"}:
            return "Access denied"
        report = await analytics_service.get_latest_summary()
        return str(report)

    @tool
    async def manager_run_nurturing_batch(query: str, config: RunnableConfig) -> str:
        """Execute an on-demand nurturing batch for warm/cold leads.

        Selects eligible leads and enqueues nurturing messages.
        Manager-only operation.
        """
        role = (config or {}).get("configurable", {}).get("role", "client")
        if role not in {"manager", "admin"}:
            return "Access denied"
        count = await nurturing_service.run_once(limit=100)
        return f"Nurturing batch executed: {count} leads"

    return [manager_get_funnel_analytics, manager_run_nurturing_batch]


@tool
@observe(name="tool-direct-response")
async def direct_response(message: str) -> str:
    """Respond directly to the user without searching.

    Use this tool for greetings, chitchat, off-topic questions,
    or when you can answer without consulting the knowledge base.
    """
    return message
