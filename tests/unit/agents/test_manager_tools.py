"""Unit tests for telegram_bot/agents/manager_tools.py."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from langchain_core.runnables import RunnableConfig

from telegram_bot.agents.manager_tools import (
    _get_user_context,
    _resolve_role,
    build_tools_for_role,
    create_crm_score_sync_tool,
    create_manager_nurturing_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(**kwargs: Any) -> RunnableConfig:
    """Build a RunnableConfig with configurable dict."""
    return RunnableConfig(configurable=kwargs)


def _passthrough_observe(name: str | None = None, **kw: Any):  # type: ignore[return]
    """Passthrough decorator replacing telegram_bot.observability.observe."""

    def dec(fn: Any) -> Any:
        return fn

    return dec


def _make_nurturing_tools(
    analytics: Any = None,
    nurturing: Any = None,
) -> list[Any]:
    """Create nurturing tools with observe mocked out."""
    import unittest.mock as mock

    with mock.patch("telegram_bot.agents.manager_tools.observe", _passthrough_observe):
        return create_manager_nurturing_tools(
            analytics_service=analytics,
            nurturing_service=nurturing,
        )


def _make_score_sync_tool(
    scoring_store: Any = None,
    kommo_client: Any = None,
    score_field_id: int = 1,
    band_field_id: int = 2,
) -> Any:
    """Create crm_score_sync tool with observe mocked out."""
    import unittest.mock as mock

    with mock.patch("telegram_bot.agents.manager_tools.observe", _passthrough_observe):
        return create_crm_score_sync_tool(
            scoring_store=scoring_store,
            kommo_client=kommo_client,
            score_field_id=score_field_id,
            band_field_id=band_field_id,
        )


# ---------------------------------------------------------------------------
# _resolve_role
# ---------------------------------------------------------------------------


class TestResolveRole:
    def test_role_from_configurable_dict(self) -> None:
        assert _resolve_role(_cfg(role="manager")) == "manager"

    def test_role_lowercased(self) -> None:
        assert _resolve_role(_cfg(role="ADMIN")) == "admin"

    def test_role_stripped(self) -> None:
        assert _resolve_role(_cfg(role="  manager  ")) == "manager"

    def test_role_from_bot_context(self) -> None:
        ctx = MagicMock()
        ctx.role = "manager"
        assert _resolve_role(_cfg(bot_context=ctx)) == "manager"

    def test_defaults_to_client_when_no_role(self) -> None:
        assert _resolve_role(_cfg()) == "client"

    def test_defaults_to_client_for_none_config(self) -> None:
        # RunnableConfig can be empty
        assert _resolve_role(RunnableConfig()) == "client"


# ---------------------------------------------------------------------------
# _get_user_context
# ---------------------------------------------------------------------------


class TestGetUserContext:
    def test_returns_user_id_and_session_id(self) -> None:
        uid, sid = _get_user_context(_cfg(user_id=42, session_id="abc"))
        assert uid == 42
        assert sid == "abc"

    def test_returns_none_when_missing(self) -> None:
        uid, sid = _get_user_context(_cfg())
        assert uid is None
        assert sid is None

    def test_returns_only_user_id(self) -> None:
        uid, sid = _get_user_context(_cfg(user_id=99))
        assert uid == 99
        assert sid is None


# ---------------------------------------------------------------------------
# build_tools_for_role
# ---------------------------------------------------------------------------


class TestBuildToolsForRole:
    def test_manager_gets_extra_tools(self) -> None:
        base = ["tool_a"]
        extra = ["tool_b", "tool_c"]
        result = build_tools_for_role(role="manager", base_tools=base, manager_tools=extra)
        assert "tool_a" in result
        assert "tool_b" in result
        assert "tool_c" in result

    def test_client_does_not_get_extra_tools(self) -> None:
        base = ["tool_a"]
        extra = ["tool_b"]
        result = build_tools_for_role(role="client", base_tools=base, manager_tools=extra)
        assert "tool_a" in result
        assert "tool_b" not in result

    def test_admin_does_not_get_extra_tools(self) -> None:
        # build_tools_for_role only checks for "manager"
        result = build_tools_for_role(role="admin", base_tools=[], manager_tools=["x"])
        assert "x" not in result

    def test_returns_new_list_not_same_object(self) -> None:
        base = ["tool_a"]
        result = build_tools_for_role(role="client", base_tools=base, manager_tools=[])
        assert result is not base


# ---------------------------------------------------------------------------
# create_manager_nurturing_tools
# ---------------------------------------------------------------------------


class TestCreateManagerNurturingTools:
    def test_returns_two_tools(self) -> None:
        tools = _make_nurturing_tools()
        assert len(tools) == 2

    async def test_analytics_access_denied_for_client(self) -> None:
        tools = _make_nurturing_tools()
        result = await tools[0].ainvoke({"query": "stats"}, config=_cfg(role="client"))
        assert result == "Access denied"

    async def test_analytics_unavailable_when_service_none(self) -> None:
        tools = _make_nurturing_tools(analytics=None)
        result = await tools[0].ainvoke({"query": "stats"}, config=_cfg(role="manager"))
        assert result == "Analytics service unavailable"

    async def test_analytics_calls_get_latest_summary(self) -> None:
        svc = AsyncMock()
        svc.get_latest_summary.return_value = "report data"
        tools = _make_nurturing_tools(analytics=svc)
        result = await tools[0].ainvoke({"query": "stats"}, config=_cfg(role="manager"))
        assert "report data" in result
        svc.get_latest_summary.assert_awaited_once()

    async def test_nurturing_access_denied_for_client(self) -> None:
        tools = _make_nurturing_tools()
        result = await tools[1].ainvoke({"query": "run"}, config=_cfg(role="client"))
        assert result == "Access denied"

    async def test_nurturing_unavailable_when_service_none(self) -> None:
        tools = _make_nurturing_tools(nurturing=None)
        result = await tools[1].ainvoke({"query": "run"}, config=_cfg(role="manager"))
        assert result == "Nurturing service unavailable"

    async def test_nurturing_returns_count(self) -> None:
        svc = AsyncMock()
        svc.run_once.return_value = 7
        tools = _make_nurturing_tools(nurturing=svc)
        result = await tools[1].ainvoke({"query": "run"}, config=_cfg(role="manager"))
        assert "7" in result


# ---------------------------------------------------------------------------
# create_crm_score_sync_tool
# ---------------------------------------------------------------------------


class TestCreateCrmScoreSyncTool:
    async def test_access_denied_for_client(self) -> None:
        import unittest.mock as mock

        with (
            mock.patch(
                "telegram_bot.agents.manager_tools.sync_pending_lead_scores",
                new_callable=AsyncMock,
            ),
            mock.patch("telegram_bot.agents.manager_tools.observe", _passthrough_observe),
        ):
            tool = _make_score_sync_tool()
            result = await tool.ainvoke({"query": "sync"}, config=_cfg(role="client"))
        assert result == "Access denied"

    async def test_manager_can_sync(self) -> None:
        import unittest.mock as mock

        mock_sync = AsyncMock(return_value={"synced": 3, "failed": 0, "skipped": 1})
        with (
            mock.patch(
                "telegram_bot.agents.manager_tools.sync_pending_lead_scores",
                mock_sync,
            ),
            mock.patch("telegram_bot.agents.manager_tools.observe", _passthrough_observe),
        ):
            tool = create_crm_score_sync_tool(
                scoring_store=None,
                kommo_client=None,
                score_field_id=1,
                band_field_id=2,
            )
            result = await tool.ainvoke(
                {"query": "sync"}, config=_cfg(role="manager", user_id=5, session_id="s1")
            )
        assert "synced 3" in result
        assert "failed 0" in result

    async def test_result_contains_user_context(self) -> None:
        import unittest.mock as mock

        mock_sync = AsyncMock(return_value={"synced": 1, "failed": 0, "skipped": 0})
        with (
            mock.patch(
                "telegram_bot.agents.manager_tools.sync_pending_lead_scores",
                mock_sync,
            ),
            mock.patch("telegram_bot.agents.manager_tools.observe", _passthrough_observe),
        ):
            tool = create_crm_score_sync_tool(
                scoring_store=None,
                kommo_client=None,
                score_field_id=1,
                band_field_id=2,
            )
            result = await tool.ainvoke(
                {"query": "sync"}, config=_cfg(role="admin", user_id=99, session_id="xyz")
            )
        assert "99" in result
        assert "xyz" in result
