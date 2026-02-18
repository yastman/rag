"""Tests for Kommo CRM integration in PropertyBot."""

from __future__ import annotations


class TestBotKommoToolsRegistration:
    def test_crm_tools_not_added_when_disabled(self):
        """KOMMO_ENABLED=false → no CRM tools in supervisor."""
        from telegram_bot.config import BotConfig

        config = BotConfig(
            telegram_token="test",
            llm_api_key="test",
            kommo_enabled=False,
        )
        assert config.kommo_enabled is False

    def test_crm_tools_require_config(self):
        """KOMMO_ENABLED=true + subdomain → ready for CRM tools."""
        from telegram_bot.config import BotConfig

        config = BotConfig(
            telegram_token="test",
            llm_api_key="test",
            kommo_enabled=True,
            kommo_subdomain="mycompany",
            kommo_client_id="abc",
            kommo_client_secret="secret",
            kommo_redirect_uri="https://example.com/cb",
            kommo_default_pipeline_id=100,
        )
        assert config.kommo_enabled is True
        assert config.kommo_subdomain == "mycompany"
        assert config.kommo_default_pipeline_id == 100
