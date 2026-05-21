"""Shared tool assembly helper for the bot agent pipeline.

Consolidates the duplicated tool-list construction from _handle_query_supervisor,
handle_hitl_callback, and handle_menu_action into a single reusable function.
"""

from __future__ import annotations

from typing import Any


def build_agent_tools(
    *,
    role: str,
    config: Any,
    history_service: Any | None,
    funnel_analytics_service: Any | None,
    nurturing_service: Any | None,
    lead_scoring_store: Any | None,
    kommo_client: Any | None,
) -> list[Any]:
    """Build the full tools list for a bot agent invocation.

    Parameters
    ----------
    role:
        User role ("client" or "manager").
    config:
        BotConfig instance (needs kommo_enabled, kommo_lead_score_field_id,
        kommo_lead_band_field_id).
    history_service:
        History service instance (None if unavailable).
    funnel_analytics_service:
        Funnel analytics service for nurturing tools.
    nurturing_service:
        Nurturing service for manager tools.
    lead_scoring_store:
        Lead scoring store for CRM score sync tool.
    kommo_client:
        Kommo CRM client (None if unavailable).

    Returns
    -------
    list[Any]
        Assembled tools list ready for create_bot_agent().
    """
    from .apartment_tools import apartment_search
    from .rag_tool import rag_search
    from .utility_tools import get_utility_tools

    if role not in ("client", "manager"):
        raise ValueError(f"Unknown role {role!r}; expected 'client' or 'manager'")

    base_tools: list[Any] = [rag_search, apartment_search]

    if role == "manager":
        from .manager_tools import (
            build_tools_for_role,
            create_crm_score_sync_tool,
            create_manager_nurturing_tools,
        )

        manager_tools: list[Any] = []

        if history_service is not None:
            from .history_tool import history_search

            manager_tools.append(history_search)

        manager_tools.extend(
            create_manager_nurturing_tools(
                analytics_service=funnel_analytics_service,
                nurturing_service=nurturing_service,
            )
        )

        if lead_scoring_store is not None:
            manager_tools.append(
                create_crm_score_sync_tool(
                    scoring_store=lead_scoring_store,
                    kommo_client=kommo_client,
                    score_field_id=config.kommo_lead_score_field_id,
                    band_field_id=config.kommo_lead_band_field_id,
                )
            )

        if getattr(config, "kommo_enabled", False) and kommo_client:
            from .crm_tools import get_crm_tools

            manager_tools.extend(get_crm_tools())

        tools = build_tools_for_role(
            role=role,
            base_tools=base_tools,
            manager_tools=manager_tools,
        )
    else:
        tools = base_tools

    tools.extend(get_utility_tools())
    return tools
