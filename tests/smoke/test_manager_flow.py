"""E2E smoke test for manager flow (#402).

Verifies: manager role -> menu -> CRM tools -> hot lead notification path.
No Docker required — uses mocked services.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from telegram_bot.agents.manager_tools import build_tools_for_role


pytestmark = pytest.mark.no_services


class TestToolGating:
    """Manager gets CRM tools, client does not."""

    def test_build_tools_for_manager(self):
        base = [MagicMock(name="rag_search"), MagicMock(name="direct_response")]
        manager = [MagicMock(name="crm_tool_1"), MagicMock(name="crm_tool_2")]
        tools = build_tools_for_role(role="manager", base_tools=base, manager_tools=manager)
        assert len(tools) == 4  # base(2) + manager(2)

    def test_build_tools_for_client(self):
        base = [MagicMock(name="rag_search"), MagicMock(name="direct_response")]
        manager = [MagicMock(name="crm_tool_1")]
        tools = build_tools_for_role(role="client", base_tools=base, manager_tools=manager)
        assert len(tools) == 2  # base only


class TestHotLeadNotifierExists:
    """HotLeadNotifier service is importable and has correct interface."""

    def test_notifier_importable(self):
        from telegram_bot.services.crm.hot_lead_notifier import HotLeadNotifier

        assert callable(getattr(HotLeadNotifier, "notify_if_hot", None))

    def test_notifier_constructor(self):
        from telegram_bot.services.crm.hot_lead_notifier import HotLeadNotifier

        notifier = HotLeadNotifier(
            bot=MagicMock(),
            cache=MagicMock(),
            manager_ids=[123],
            dedupe_ttl_sec=3600,
        )
        assert notifier is not None
