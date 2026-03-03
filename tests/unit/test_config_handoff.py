from telegram_bot.config import BotConfig


def test_handoff_config_defaults():
    """Handoff config has sensible defaults when env vars not set."""
    cfg = BotConfig(
        telegram_bot_token="test:token",  # required field
        _env_file=None,
    )
    assert cfg.managers_group_id is None
    assert cfg.handoff_ttl_hours == 72
    assert cfg.handoff_summary_min_messages == 3
    assert cfg.business_hours_start == 9
    assert cfg.business_hours_end == 18
    assert cfg.business_hours_tz == "Europe/Sofia"
    assert cfg.handoff_wait_timeout_min == 15


def test_handoff_config_from_env(monkeypatch):
    """Handoff config reads from environment variables."""
    monkeypatch.setenv("MANAGERS_GROUP_ID", "-1001234567890")
    monkeypatch.setenv("HANDOFF_TTL_HOURS", "12")
    monkeypatch.setenv("HANDOFF_SUMMARY_MIN_MESSAGES", "5")
    cfg = BotConfig(
        telegram_bot_token="test:token",
        _env_file=None,
    )
    assert cfg.managers_group_id == -1001234567890
    assert cfg.handoff_ttl_hours == 12
    assert cfg.handoff_summary_min_messages == 5
