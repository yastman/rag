"""Tests for bot Mini App URL config field."""

from telegram_bot.config import BotConfig


def test_config_has_mini_app_url():
    assert "mini_app_url" in BotConfig.model_fields


def test_mini_app_url_default_empty():
    field = BotConfig.model_fields["mini_app_url"]
    assert field.default == ""
