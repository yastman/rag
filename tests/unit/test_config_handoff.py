import pytest
from pydantic import ValidationError

from telegram_bot.config import BotConfig


def test_handoff_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("HANDOFF_ENABLED", raising=False)
    cfg = BotConfig(telegram_bot_token="test:token", _env_file=None)
    assert cfg.handoff_enabled is False


def test_handoff_enabled_reads_env(monkeypatch):
    monkeypatch.setenv("HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MANAGERS_GROUP_ID", "-1001234567890")
    cfg = BotConfig(telegram_bot_token="test:token", _env_file=None)
    assert cfg.handoff_enabled is True


def test_handoff_enabled_requires_managers_group_id(monkeypatch):
    monkeypatch.setenv("HANDOFF_ENABLED", "true")
    monkeypatch.delenv("MANAGERS_GROUP_ID", raising=False)

    with pytest.raises(
        ValidationError, match="HANDOFF_ENABLED=true but MANAGERS_GROUP_ID is missing"
    ):
        BotConfig(telegram_bot_token="test:token", _env_file=None)


def test_handoff_enabled_allows_valid_managers_group_id(monkeypatch):
    monkeypatch.setenv("HANDOFF_ENABLED", "true")
    monkeypatch.setenv("MANAGERS_GROUP_ID", "-1001234567890")

    cfg = BotConfig(telegram_bot_token="test:token", _env_file=None)

    assert cfg.handoff_enabled is True
    assert cfg.managers_group_id == -1001234567890


def test_handoff_disabled_does_not_require_managers_group_id(monkeypatch):
    monkeypatch.setenv("HANDOFF_ENABLED", "false")
    monkeypatch.delenv("MANAGERS_GROUP_ID", raising=False)

    cfg = BotConfig(telegram_bot_token="test:token", _env_file=None)

    assert cfg.handoff_enabled is False


def test_handoff_config_defaults(monkeypatch):
    """Handoff config has sensible defaults when env vars not set."""
    monkeypatch.delenv("MANAGERS_GROUP_ID", raising=False)
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
    monkeypatch.setenv("HANDOFF_ENABLED", "true")
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
