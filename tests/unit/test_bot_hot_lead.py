"""Regression test for retired hot-lead bot wiring (#2625)."""

from __future__ import annotations

from telegram_bot.config import BotConfig
from tests.unit._property_bot_factory import make_property_bot


def _make_config() -> BotConfig:
    return BotConfig(
        _env_file=None,
        telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
        llm_api_key="llm-key",
        llm_model="gpt-4o-mini",
        qdrant_url="http://localhost:6333",
        redis_url="redis://localhost:6379",
        rerank_provider="none",
        manager_ids=[123],
        manager_hot_lead_threshold=60,
        manager_hot_lead_dedupe_sec=3600,
    )


def test_bot_has_no_removed_notifier_attribute() -> None:
    """PropertyBot intentionally no longer declares _hot_lead_notifier (#2625)."""
    bot = make_property_bot(_make_config())

    assert not hasattr(bot, "_hot_lead_notifier")
