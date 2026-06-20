"""Shared tool assembly helper for the bot agent pipeline.

Consolidates the duplicated tool-list construction from _handle_query_supervisor
and handle_menu_action into a single reusable function.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .context import get_bot_context
from .tooling import RunnableConfig


def _resolve_role(config: RunnableConfig) -> str:
    configurable = (config or {}).get("configurable", {})
    role = configurable.get("role")
    if isinstance(role, str) and role.strip():
        return role.strip().lower()
    ctx = get_bot_context(None, config)
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


def build_agent_tools(
    *,
    role: str,
    config: Any,
) -> list[Any]:
    """Build the full tools list for a bot agent invocation.

    Parameters
    ----------
    role:
        User role ("client" or "manager").
    config:
        BotConfig instance.

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
        tools = build_tools_for_role(
            role=role,
            base_tools=base_tools,
            manager_tools=[],
        )
    else:
        tools = base_tools

    tools.extend(get_utility_tools())
    return tools
