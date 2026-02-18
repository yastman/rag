"""Tests for Kommo CRM config fields."""

from __future__ import annotations


class TestKommoConfig:
    def test_kommo_disabled_by_default(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(telegram_token="test", llm_api_key="test")
        assert config.kommo_enabled is False

    def test_kommo_config_fields_exist(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(
            telegram_token="test",
            llm_api_key="test",
            kommo_enabled=True,
            kommo_subdomain="mycompany",
            kommo_client_id="abc123",
            kommo_client_secret="secret",
            kommo_redirect_uri="https://example.com/callback",
            kommo_default_pipeline_id=100,
        )
        assert config.kommo_enabled is True
        assert config.kommo_subdomain == "mycompany"
        assert config.kommo_client_id == "abc123"
        assert config.kommo_client_secret.get_secret_value() == "secret"
        assert config.kommo_redirect_uri == "https://example.com/callback"
        assert config.kommo_default_pipeline_id == 100

    def test_kommo_auth_code_optional(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(telegram_token="test", llm_api_key="test")
        assert config.kommo_auth_code == ""

    def test_kommo_responsible_user_id_optional(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(telegram_token="test", llm_api_key="test")
        assert config.kommo_responsible_user_id is None

    def test_kommo_session_field_id_default(self):
        from telegram_bot.config import BotConfig

        config = BotConfig(telegram_token="test", llm_api_key="test")
        assert config.kommo_session_field_id == 0
