"""E2E smoke test for manager flow (#402).

Verifies the manager-flow service surface: HotLeadNotifier importability and
constructor contract. No Docker required — uses mocked services.

#3216: the agent tool-gating assertions were removed together with the
imperative agent tool registry they exercised.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.no_services


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
