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

    def test_config_derives_local_redis_url_from_password(self, monkeypatch):
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.setenv("REDIS_PASSWORD", "dev_redis_pass")

        from telegram_bot.config import BotConfig

        config = BotConfig(_env_file=None)
        assert config.redis_url == "redis://:dev_redis_pass@localhost:6379"

    def test_config_constructor_kwargs(self):
        """Ensure BotConfig can be created with python field names (backward compat)."""
        from telegram_bot.config import BotConfig

        config = BotConfig(
            telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
            llm_api_key="test-key",
            llm_base_url="http://fake:4000",
            search_top_k=42,
        )

        assert config.telegram_token == "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"
        assert config.search_top_k == 42

    def test_config_bool_fields_parse_env_strings(self, monkeypatch):
        """Bool fields should parse 'true'/'false' strings from env."""
        monkeypatch.setenv("VOICE_ENABLED", "true")
        monkeypatch.setenv("CONTENT_FILTER_ENABLED", "false")

        from telegram_bot.config import BotConfig

        config = BotConfig()
        assert config.voice_enabled is True
        assert config.content_filter_enabled is False

    def test_manager_ids_empty_env_does_not_crash(self, monkeypatch):
        """Empty MANAGER_IDS should be treated as no managers, not JSON parse error."""
        monkeypatch.setenv("MANAGER_IDS", "")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(
            _env_file=None,
            telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
            llm_api_key="test-key",
        )
        assert cfg.manager_ids == []

    def test_manager_ids_csv_env_is_parsed(self, monkeypatch):
        """MANAGER_IDS supports comma-separated Telegram IDs."""
        monkeypatch.setenv("MANAGER_IDS", "123, 456,not_a_number, 789")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(
            _env_file=None,
            telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
            llm_api_key="test-key",
        )
        assert cfg.manager_ids == [123, 456, 789]

    def test_admin_ids_empty_env_does_not_crash(self, monkeypatch):
        """Empty ADMIN_IDS should be treated as no admins, not JSON parse error."""
        monkeypatch.setenv("ADMIN_IDS", "")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(
            _env_file=None,
            telegram_token="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
            llm_api_key="test-key",
        )
        assert cfg.admin_ids == []

    def test_config_get_collection_name(self):
        """get_collection_name() still works after migration."""
        from telegram_bot.config import BotConfig

        config = BotConfig(qdrant_collection="test_col", qdrant_quantization_mode="scalar")
        assert config.get_collection_name() == "test_col_scalar"

        config2 = BotConfig(qdrant_collection="test_col", qdrant_quantization_mode="off")
        assert config2.get_collection_name() == "test_col"

    def test_handoff_enabled_empty_env_treated_as_false(self, monkeypatch):
        """Empty handoff flag should be treated as disabled."""
        monkeypatch.setenv("HANDOFF_ENABLED", "")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=None)
        assert cfg.handoff_enabled is False

    def test_managers_group_id_empty_string_does_not_crash(self, monkeypatch):
        """Empty MANAGERS_GROUP_ID should parse as None, not crash (#2149).

        Pass handoff_enabled=False via constructor kwarg to isolate from the
        running environment (where HANDOFF_ENABLED may be set to true).
        """
        monkeypatch.setenv("MANAGERS_GROUP_ID", "")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(handoff_enabled=False, _env_file=None)
        assert cfg.managers_group_id is None

    def test_redis_url_infers_password_loaded_from_env_file(self, monkeypatch, tmp_path):
        """REDIS_PASSWORD loaded from dotenv should drive the native local default URL."""
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("REDIS_PASSWORD", raising=False)

        env_file = tmp_path / ".env.bot"
        env_file.write_text("REDIS_PASSWORD=dotenv_secret\n", encoding="utf-8")

        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=env_file)
        assert cfg.redis_url == "redis://:dotenv_secret@localhost:6379"


class TestBotConfigLiveSchemaDefaults:
    """Serialization/default snapshot of the live BotConfig schema (#3350).

    Pins every field the Telegram runtime actually reads, with its default.
    Ignored knobs removed in #3350 must not reappear here; their removal is
    asserted by test_bot_config_removed_knobs_3350.py.
    """

    EXPECTED_DEFAULTS: dict[str, object] = {
        # Telegram
        "telegram_token": "",
        # Services
        "bge_m3_url": "http://localhost:8000",
        "redis_password": "",
        "redis_url": "redis://localhost:6379",
        "qdrant_url": "http://localhost:6333",
        "qdrant_api_key": None,
        "qdrant_collection": "gdrive_documents_bge",
        # LLM
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "gpt-4o-mini",
        # Search / rerank (live surface preserved by #3350)
        "search_top_k": 40,
        "rerank_provider": "colbert",
        "qdrant_timeout": 30,
        "qdrant_quantization_mode": "off",
        # Admin / domain
        "admin_ids": [],
        "domain": "недвижимость",
        "domain_language": "ru",
        # Voice
        "voice_enabled": False,
        "show_transcription": True,
        "voice_language": "ru",
        "stt_model": "whisper",
        "voice_timeout": 30,
        # Content filter
        "content_filter_enabled": True,
        "guard_mode": "hard",
        # Apartment extraction
        "apartment_extraction_model": "gpt-4o-mini",
        # CRM database
        "realestate_database_url": "",
        # Managers
        "manager_ids": [],
        # Handoff
        "handoff_enabled": False,
        "managers_group_id": None,
        "handoff_ttl_hours": 72,
        "handoff_summary_min_messages": 3,
        "business_hours_start": 9,
        "business_hours_end": 18,
        "business_hours_tz": "Europe/Sofia",
    }

    def test_live_fields_keep_defaults(self):
        """Every live field must keep its documented default."""
        from telegram_bot.config import BotConfig

        cfg = BotConfig(_env_file=None)
        for field, expected in self.EXPECTED_DEFAULTS.items():
            actual = getattr(cfg, field)
            if field == "redis_password":
                actual = actual.get_secret_value()
            assert actual == expected, f"{field}: expected {expected!r}, got {actual!r}"

    def test_no_untracked_schema_growth(self):
        """BotConfig must not grow fields outside the pinned live schema."""
        from telegram_bot.config import BotConfig

        unexpected = set(BotConfig.model_fields) - set(self.EXPECTED_DEFAULTS)
        assert not unexpected, (
            "BotConfig grew fields beyond the live schema; either the runtime "
            f"reads them (pin them here with defaults) or remove them: {sorted(unexpected)}"
        )
