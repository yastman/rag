"""Focused tests for manager_tools helper branches."""

from __future__ import annotations

from telegram_bot.agents.manager_tools import _get_user_context, _resolve_role, build_tools_for_role


def test_resolve_role_uses_bot_context_when_explicit_role_missing() -> None:
    class Ctx:
        role = "Admin"

    assert _resolve_role({"configurable": {"bot_context": Ctx()}}) == "admin"


def test_get_user_context_defaults_to_none() -> None:
    assert _get_user_context({}) == (None, None)


def test_build_tools_for_role_excludes_manager_tools_for_admin() -> None:
    tools = build_tools_for_role(role="admin", base_tools=["base"], manager_tools=["mgr"])

    assert tools == ["base"]
