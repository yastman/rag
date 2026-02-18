"""Manager-only supervisor tools (#388).

Provides tools available exclusively to users with the 'manager' role.
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import tool


def create_manager_tools(*, lead_service: Any) -> list[Any]:
    """Create manager-specific tools with injected lead service."""

    @tool
    async def manager_list_hot_leads(limit: int = 10) -> str:
        """List latest hot leads for manager triage."""
        leads = await lead_service.list_hot_leads(limit=limit)
        if not leads:
            return "No hot leads right now."
        return "\n".join(f"{row['lead_id']}: score={row['score']}" for row in leads)

    @tool
    async def manager_ack_hot_lead(lead_id: int) -> str:
        """Mark hot lead as acknowledged by manager."""
        await lead_service.ack_hot_lead(lead_id=lead_id)
        return f"Lead {lead_id} acknowledged"

    return [manager_list_hot_leads, manager_ack_hot_lead]
