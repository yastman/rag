"""Manager-only tools and role-gating helpers."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from telegram_bot.agents.context import get_bot_context
from telegram_bot.agents.tooling import RunnableConfig


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


def build_tools_for_role(
    *, role: str, base_tools: list[Any], manager_tools: Iterable[Any]
) -> list[Any]:
    """Select tools based on user role."""
    tools = list(base_tools)
    if role == "manager":
        tools.extend(list(manager_tools))
    return tools
