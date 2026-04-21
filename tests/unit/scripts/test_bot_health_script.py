"""Regression guards for scripts/test_bot_health.sh local contract."""

from pathlib import Path


SCRIPT = Path("scripts/test_bot_health.sh")


def test_bot_health_uses_botconfig_and_redis_sdk_for_auth_contract() -> None:
    """Local preflight must reuse BotConfig + redis.from_url for Redis auth checks."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "from telegram_bot.config import BotConfig" in text
    assert "redis.from_url(config.redis_url" in text


def test_bot_health_keeps_litellm_liveliness_probe() -> None:
    """The LLM preflight should keep the liveliness endpoint check path."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "/health/liveliness" in text


def test_bot_health_reports_local_postgres_expectation() -> None:
    """The local preflight should surface the optional localhost Postgres contract."""
    text = SCRIPT.read_text(encoding="utf-8")
    assert "REAL_ESTATE_DATABASE_URL" in text
    assert "localhost:5432" in text
    assert "optional" in text.lower()
