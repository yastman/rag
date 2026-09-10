"""Test HotLeadNotifier surface after bot wiring removal (#402, #2625)."""

from __future__ import annotations

from telegram_bot.config import BotConfig
from tests.unit._property_bot_factory import make_property_bot


def _make_config() -> BotConfig:
    return BotConfig(
        _env_file=None,
        telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        llm_api_key="llm-key",
        llm_base_url="https://api.example.com/v1",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
        manager_ids=[123],
        manager_hot_lead_threshold=60,
        manager_hot_lead_dedupe_sec=3600,
    )


class TestHotLeadNotifierWiring:
    """HotLeadNotifier remains importable; bot no longer owns the attribute (#2625)."""

    def test_bot_has_no_removed_notifier_attribute(self):
        """PropertyBot intentionally no longer declares _hot_lead_notifier (#2625)."""
        bot = make_property_bot(_make_config())
        assert not hasattr(bot, "_hot_lead_notifier")

    def test_notifier_importable_and_has_interface(self):
        """HotLeadNotifier is importable and has notify_if_hot method."""
        from telegram_bot.services.crm.hot_lead_notifier import HotLeadNotifier

        assert hasattr(HotLeadNotifier, "notify_if_hot")
        assert callable(getattr(HotLeadNotifier, "notify_if_hot", None))
