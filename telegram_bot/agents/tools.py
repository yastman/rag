"""Supervisor tools with runtime user context (#240).

Each tool reads user_id/session_id from RunnableConfig.configurable
and delegates to existing services (RAG graph, HistoryService).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import observe
from telegram_bot.services.kommo_models import LeadScoreSyncPayload


logger = logging.getLogger(__name__)


def _get_user_context(config: RunnableConfig) -> tuple[int | None, str | None]:
    """Extract user_id and session_id from RunnableConfig."""
    configurable = (config or {}).get("configurable", {})
    user_id = configurable.get("user_id")
    session_id = configurable.get("session_id")
    return user_id, session_id


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
            key = f"lead-score:{rec.lead_id}:{rec.session_id}:{rec.score_value}:{rec.score_band}"
            payload = LeadScoreSyncPayload.from_record(
                rec,
                score_field_id=score_field_id,
                band_field_id=band_field_id,
            ).to_kommo_payload()
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
