"""Test that confirmed-stale BotConfig fields have been removed (issue #2695)."""

from telegram_bot.config import BotConfig


def test_handoff_wait_timeout_min_removed():
    """HANDOFF_WAIT_TIMEOUT_MIN has zero live callers; must be removed (#2695)."""
    assert "handoff_wait_timeout_min" not in BotConfig.model_fields, (
        "handoff_wait_timeout_min is a stale field with zero production callers; "
        "it should not exist in BotConfig."
    )
