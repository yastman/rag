"""Unit tests for src/config/settings.py."""

import os
from unittest.mock import patch

import pytest

from src.config.constants import APIProvider, ModelName, SearchEngine
from src.config.settings import Settings


class TestSettingsInitialization:
    """Test Settings class initialization."""

    def test_settings_default_values(self):
        """Test that Settings loads default values correctly."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")

            assert settings.temperature == 0.0
            assert settings.max_tokens == 4096
            assert settings.qdrant_url == "http://localhost:6333"
            assert settings.score_threshold == 0.3
            assert settings.top_k == 10

    def test_settings_env_override(self):
        """Test that environment variables override defaults."""
        env_vars = {
            "API_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-key",
            "QDRANT_URL": "http://custom-qdrant:6333",
            "COLLECTION_NAME": "test_collection",
            "ENABLE_CACHING": "false",
            "DEBUG": "true",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings()

            assert settings.api_provider == APIProvider.OPENAI
            assert settings.qdrant_url == "http://custom-qdrant:6333"
            assert settings.collection_name == "test_collection"
            assert settings.enable_caching is False
            assert settings.debug is True

    def test_settings_constructor_override(self):
        """Test that constructor arguments override env vars."""
        env_vars = {
            "API_PROVIDER": "openai",
            "OPENAI_API_KEY": "env-key",
            "QDRANT_URL": "http://env-qdrant:6333",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings(
                qdrant_url="http://constructor-qdrant:6333",
                score_threshold=0.5,
                top_k=20,
            )

            assert settings.qdrant_url == "http://constructor-qdrant:6333"
            assert settings.score_threshold == 0.5
            assert settings.top_k == 20


class TestAPIKeyValidation:
    """Test API key validation logic."""

    @staticmethod
    def _fresh_settings():
        """Import Settings from current sys.modules to avoid stale references.

        Other tests (test_contextualized_embeddings, test_settings_lazy) may
        reload or replace src.config.settings in sys.modules. A module-level
        ``from src.config.settings import Settings`` captures the OLD class
        whose __init__.__globals__ points to the old module dict. Patching
        ``src.config.settings.load_dotenv`` only affects the NEW module, so
        the real load_dotenv runs, loads .env with real API keys, and the
        test never raises.
        """
        import importlib

        mod = importlib.import_module("src.config.settings")
        return mod.Settings

    def test_claude_provider_requires_anthropic_key(self):
        """Test that Claude provider requires ANTHROPIC_API_KEY."""
        _Settings = self._fresh_settings()
        with patch("src.config.settings.load_dotenv"):  # Don't load .env
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not set"):
                    _Settings(api_provider="claude")

    def test_openai_provider_requires_openai_key(self):
        """Test that OpenAI provider requires OPENAI_API_KEY."""
        _Settings = self._fresh_settings()
        with patch("src.config.settings.load_dotenv"):  # Don't load .env
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(ValueError, match="OPENAI_API_KEY not set"):
                    _Settings(api_provider="openai")

    def test_groq_provider_requires_groq_key(self):
        """Test that Groq provider requires GROQ_API_KEY."""
        _Settings = self._fresh_settings()
        with patch("src.config.settings.load_dotenv"):  # Don't load .env
            with patch.dict(os.environ, {}, clear=True):
                with pytest.raises(ValueError, match="GROQ_API_KEY not set"):
                    _Settings(api_provider="groq")

    def test_valid_api_key_does_not_raise(self):
        """Test that valid API key does not raise error."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "valid-key"}, clear=False):
            settings = Settings(api_provider="openai")
            assert settings.openai_api_key == "valid-key"


class TestDefaultModelSelection:
    """Test default model selection for providers."""

    def test_claude_default_model(self):
        """Test default model for Claude provider."""
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="claude")
            assert settings.model_name == ModelName.CLAUDE_SONNET.value

    def test_openai_default_model(self):
        """Test default model for OpenAI provider."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            assert settings.model_name == ModelName.GPT_4_TURBO.value

    def test_groq_default_model(self):
        """Test default model for Groq provider."""
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="groq")
            assert settings.model_name == ModelName.GROQ_LLAMA3_70B.value

    def test_custom_model_override(self):
        """Test that custom model overrides default."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai", model_name="gpt-4")
            assert settings.model_name == "gpt-4"


class TestSearchEngineConfiguration:
    """Test search engine configuration."""

    def test_default_search_engine(self):
        """Test default search engine is HYBRID_RRF_COLBERT."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            assert settings.search_engine == SearchEngine.HYBRID_RRF_COLBERT

    def test_search_engine_from_env(self):
        """Test search engine from environment variable."""
        env_vars = {
            "OPENAI_API_KEY": "test-key",
            "SEARCH_ENGINE": "baseline",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings(api_provider="openai")
            assert settings.search_engine == SearchEngine.BASELINE

    def test_search_engine_from_constructor(self):
        """Test search engine from constructor."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai", search_engine="hybrid_rrf")
            assert settings.search_engine == SearchEngine.HYBRID_RRF


class TestFeatureFlags:
    """Test feature flag parsing."""

    def test_feature_flags_default_true(self):
        """Test that feature flags default to true."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")

            assert settings.enable_caching is True
            assert settings.enable_query_expansion is True
            assert settings.enable_mlflow is True
            assert settings.enable_langfuse is True

    def test_feature_flags_false_parsing(self):
        """Test that 'false' string is parsed correctly."""
        env_vars = {
            "OPENAI_API_KEY": "test-key",
            "ENABLE_CACHING": "false",
            "ENABLE_MLFLOW": "FALSE",
            "ENABLE_LANGFUSE": "False",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings(api_provider="openai")

            assert settings.enable_caching is False
            assert settings.enable_mlflow is False
            assert settings.enable_langfuse is False


class TestToDict:
    """Test settings serialization."""

    def test_to_dict_excludes_sensitive_data(self):
        """Test that to_dict excludes API keys."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "secret-key"}, clear=False):
            settings = Settings(api_provider="openai")
            result = settings.to_dict()

            assert "openai_api_key" not in result
            assert "anthropic_api_key" not in result
            assert "groq_api_key" not in result
            assert "qdrant_api_key" not in result

    def test_to_dict_includes_config(self):
        """Test that to_dict includes configuration values."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            result = settings.to_dict()

            assert "api_provider" in result
            assert "model_name" in result
            assert "search_engine" in result
            assert "qdrant_url" in result
            assert result["api_provider"] == "openai"


class TestRepr:
    """Test string representation."""

    def test_repr_format(self):
        """Test __repr__ returns formatted string."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            result = repr(settings)

            assert "Settings(" in result
            assert "api_provider=openai" in result
            assert "search_engine=" in result


# === BotConfig (telegram_bot) pydantic-settings tests ===


class TestBotConfigIsPydanticSettings:
    """Test that BotConfig is a pydantic-settings BaseSettings subclass."""

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
