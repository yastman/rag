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

    def test_manager_hot_lead_defaults(self):
        """Manager hot-lead config fields have sane defaults (#388)."""
        from telegram_bot.config import BotConfig

        cfg = BotConfig()
        assert cfg.manager_hot_lead_threshold == 60
        assert cfg.manager_hot_lead_dedupe_sec == 3600

    def test_manager_ids_empty_env_does_not_crash(self, monkeypatch):
        """Empty MANAGER_IDS should be treated as no managers, not JSON parse error."""
        monkeypatch.setenv("MANAGER_IDS", "")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=None, telegram_token="test-token", llm_api_key="test-key")
        assert cfg.manager_ids == []

    def test_manager_ids_csv_env_is_parsed(self, monkeypatch):
        """MANAGER_IDS supports comma-separated Telegram IDs."""
        monkeypatch.setenv("MANAGER_IDS", "123, 456,not_a_number, 789")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=None, telegram_token="test-token", llm_api_key="test-key")
        assert cfg.manager_ids == [123, 456, 789]

    def test_admin_ids_empty_env_does_not_crash(self, monkeypatch):
        """Empty ADMIN_IDS should be treated as no admins, not JSON parse error."""
        monkeypatch.setenv("ADMIN_IDS", "")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=None, telegram_token="test-token", llm_api_key="test-key")
        assert cfg.admin_ids == []

    def test_agent_checkpointer_ttl_default(self):
        """agent_checkpointer_ttl_minutes defaults to 120 (#424)."""
        from telegram_bot.config import BotConfig

        cfg = BotConfig()
        assert cfg.agent_checkpointer_ttl_minutes == 120

    def test_agent_checkpointer_ttl_env_var(self, monkeypatch):
        """AGENT_CHECKPOINTER_TTL_MINUTES overrides default (#424)."""
        monkeypatch.setenv("AGENT_CHECKPOINTER_TTL_MINUTES", "60")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=None)
        assert cfg.agent_checkpointer_ttl_minutes == 60

    def test_config_get_collection_name(self):
        """get_collection_name() still works after migration."""
        from telegram_bot.config import BotConfig

        config = BotConfig(qdrant_collection="test_col", qdrant_quantization_mode="scalar")
        assert config.get_collection_name() == "test_col_scalar"

        config2 = BotConfig(qdrant_collection="test_col", qdrant_quantization_mode="off")
        assert config2.get_collection_name() == "test_col"

    def test_client_direct_pipeline_flag_default_false(self, monkeypatch):
        """Client direct pipeline should be opt-in."""
        monkeypatch.delenv("CLIENT_DIRECT_PIPELINE_ENABLED", raising=False)
        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=None)
        assert cfg.client_direct_pipeline_enabled is False

    def test_client_direct_pipeline_flag_reads_env(self, monkeypatch):
        """CLIENT_DIRECT_PIPELINE_ENABLED must map to BotConfig field."""
        monkeypatch.setenv("CLIENT_DIRECT_PIPELINE_ENABLED", "true")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=None)
        assert cfg.client_direct_pipeline_enabled is True

    def test_client_direct_pipeline_flag_empty_env_treated_as_false(self, monkeypatch):
        """Empty env var should not crash and must be treated as disabled."""
        monkeypatch.setenv("CLIENT_DIRECT_PIPELINE_ENABLED", "")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=None)
        assert cfg.client_direct_pipeline_enabled is False
