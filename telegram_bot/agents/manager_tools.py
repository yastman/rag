"""Manager-only tools and role-gating helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from telegram_bot.observability import observe
from telegram_bot.services.lead_score_sync import sync_pending_lead_scores


def _resolve_role(config: RunnableConfig) -> str:
    configurable = (config or {}).get("configurable", {})
    role = configurable.get("role")
    if isinstance(role, str) and role.strip():
        return role.strip().lower()
    ctx = configurable.get("bot_context")
    ctx_role = getattr(ctx, "role", None)
    if isinstance(ctx_role, str) and ctx_role.strip():
        return ctx_role.strip().lower()
    return "client"


def _get_user_context(config: RunnableConfig) -> tuple[int | None, str | None]:
    configurable = (config or {}).get("configurable", {})
    user_id = configurable.get("user_id")
    session_id = configurable.get("session_id")
    return user_id, session_id


def build_tools_for_role(
    *, role: str, base_tools: list[Any], manager_tools: Iterable[Any]
) -> list[Any]:
    """Select tools based on user role."""
    tools = list(base_tools)
    if role == "manager":
        tools.extend(list(manager_tools))
    return tools


def create_manager_nurturing_tools(*, analytics_service: Any, nurturing_service: Any) -> list[Any]:
    """Create manager-only nurturing + analytics tools."""

    @tool
    @observe(name="manager-get-funnel-analytics")
    async def manager_get_funnel_analytics(query: str, config: RunnableConfig) -> str:
        """Get funnel conversion analytics for manager review."""
        role = _resolve_role(config)
        if role not in {"manager", "admin"}:
            return "Access denied"
        if analytics_service is None:
            return "Analytics service unavailable"
        report = await analytics_service.get_latest_summary()
        return str(report)

    @tool
    @observe(name="manager-run-nurturing-batch")
    async def manager_run_nurturing_batch(query: str, config: RunnableConfig) -> str:
        """Execute an on-demand nurturing batch for warm/cold leads."""
        role = _resolve_role(config)
        if role not in {"manager", "admin"}:
            return "Access denied"
        if nurturing_service is None:
            return "Nurturing service unavailable"
        count = await nurturing_service.run_once(limit=100)
        return f"Nurturing batch executed: {count} leads"

    return [manager_get_funnel_analytics, manager_run_nurturing_batch]


def create_crm_score_sync_tool(
    *,
    scoring_store: Any,
    kommo_client: Any,
    score_field_id: int,
    band_field_id: int,
) -> Any:
    """Create crm_sync_lead_score production tool."""

    @tool
    @observe(name="tool-crm-sync-lead-score")
    async def crm_sync_lead_score(query: str, config: RunnableConfig) -> str:
        """Sync pending lead scores to Kommo CRM."""
        role = _resolve_role(config)
        if role not in {"manager", "admin"}:
            return "Access denied"

        user_id, session_id = _get_user_context(config)
        result = await sync_pending_lead_scores(
            scoring_store=scoring_store,
            kommo_client=kommo_client,
            score_field_id=score_field_id,
            band_field_id=band_field_id,
            limit=20,
        )
        return (
            f"CRM score sync completed: synced {result['synced']}, failed {result['failed']}, "
            f"skipped {result['skipped']} (user {user_id}, session {session_id})"
        )

    return crm_sync_lead_score
