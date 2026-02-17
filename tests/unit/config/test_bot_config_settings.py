"""Unit tests for telegram_bot.config.BotConfig settings behavior."""

import pytest


class TestBotConfigIsPydanticSettings:
    """Test that BotConfig remains a pydantic-settings BaseSettings subclass."""

    def test_config_is_pydantic_settings(self):
        from pydantic_settings import BaseSettings

        from telegram_bot.config import BotConfig

        assert issubclass(BotConfig, BaseSettings)

    def test_config_validates_types(self):
        from pydantic import ValidationError

        from telegram_bot.config import BotConfig

        with pytest.raises(ValidationError):
            BotConfig(search_top_k="not_a_number")

    def test_config_reads_env(self, monkeypatch):
        monkeypatch.setenv("BOT_DOMAIN", "тестовый домен")

        from telegram_bot.config import BotConfig

        config = BotConfig()
        assert config.domain == "тестовый домен"

    def test_config_constructor_kwargs(self):
        """Ensure BotConfig can be created with python field names (backward compat)."""
        from telegram_bot.config import BotConfig

        config = BotConfig(
            telegram_token="test-token",
            llm_api_key="test-key",
            llm_base_url="http://fake:4000",
            search_top_k=42,
        )

        assert config.telegram_token == "test-token"
        assert config.search_top_k == 42

    def test_config_bool_fields_parse_env_strings(self, monkeypatch):
        """Bool fields should parse 'true'/'false' strings from env."""
        monkeypatch.setenv("USE_HYDE", "true")
        monkeypatch.setenv("MMR_ENABLED", "false")

        from telegram_bot.config import BotConfig

        config = BotConfig()
        assert config.use_hyde is True
        assert config.mmr_enabled is False

    def test_config_get_collection_name(self):
        """get_collection_name() still works after migration."""
        from telegram_bot.config import BotConfig

        config = BotConfig(qdrant_collection="test_col", qdrant_quantization_mode="scalar")
        assert config.get_collection_name() == "test_col_scalar"

        config2 = BotConfig(qdrant_collection="test_col", qdrant_quantization_mode="off")
        assert config2.get_collection_name() == "test_col"
