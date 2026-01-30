"""Unit tests for telegram_bot/config.py."""

import os
import sys
from unittest.mock import patch

import pytest


class TestBotConfig:
    """Tests for BotConfig dataclass.

    Note: BotConfig uses os.getenv() as dataclass defaults, which are evaluated
    at class definition time (module import). To test env var behavior, we must
    reload the module with the desired environment variables set.

    Additionally, the module calls load_dotenv() on import, so we mock that
    to prevent loading values from the actual .env file.
    """

    @pytest.fixture
    def reload_config(self):
        """Fixture that reloads the config module with clean environment."""

        def _reload(env_vars: dict):
            # Remove the module from cache so it reloads with new env
            if "telegram_bot.config" in sys.modules:
                del sys.modules["telegram_bot.config"]

            # Mock load_dotenv to prevent loading actual .env file
            with patch.dict(os.environ, env_vars, clear=True):
                with patch("dotenv.load_dotenv"):
                    from telegram_bot.config import BotConfig

                    return BotConfig()

        yield _reload

        # Cleanup: remove module from cache
        if "telegram_bot.config" in sys.modules:
            del sys.modules["telegram_bot.config"]

    def test_from_env_with_all_values(self, reload_config):
        """Test loading config from environment variables."""
        env = {
            "TELEGRAM_BOT_TOKEN": "test-token-123",
            "VOYAGE_API_KEY": "voyage-key-456",
            "QDRANT_URL": "http://qdrant:6333",
            "QDRANT_COLLECTION": "test_collection",
            "QDRANT_API_KEY": "qdrant-api-key",
            "REDIS_URL": "redis://redis:6379",
            "BGE_M3_URL": "http://bge:8000",
            "LLM_API_KEY": "llm-key",
            "LLM_BASE_URL": "http://litellm:4000",
            "LLM_MODEL": "test-model",
        }
        config = reload_config(env)

        assert config.telegram_token == "test-token-123"
        assert config.voyage_api_key == "voyage-key-456"
        assert config.qdrant_url == "http://qdrant:6333"
        assert config.qdrant_collection == "test_collection"
        assert config.qdrant_api_key == "qdrant-api-key"
        assert config.redis_url == "redis://redis:6379"
        assert config.bge_m3_url == "http://bge:8000"
        assert config.llm_api_key == "llm-key"
        assert config.llm_base_url == "http://litellm:4000"
        assert config.llm_model == "test-model"

    def test_default_values(self, reload_config):
        """Test default values when env vars not set."""
        config = reload_config({})

        assert config.qdrant_url == "http://localhost:6333"
        assert config.redis_url == "redis://localhost:6379"
        assert config.bge_m3_url == "http://localhost:8000"
        assert config.llm_base_url == "https://api.cerebras.ai/v1"
        assert config.llm_model == "zai-glm-4.7"
        assert config.qdrant_collection == "contextual_bulgaria_voyage4"

    def test_telegram_token_empty_when_missing(self, reload_config):
        """Test that missing telegram token defaults to empty string."""
        config = reload_config({})
        assert config.telegram_token == ""

    def test_qdrant_api_key_none_when_missing(self, reload_config):
        """Test that missing QDRANT_API_KEY results in None, not empty string.

        This prevents 'Api key is used with an insecure connection' warning
        when connecting to Qdrant over HTTP without authentication.
        """
        config = reload_config({})
        assert config.qdrant_api_key is None

    def test_qdrant_api_key_none_when_empty(self, reload_config):
        """Test that empty QDRANT_API_KEY results in None.

        Regression test: empty string was being passed to AsyncQdrantClient,
        triggering insecure connection warning even without real API key.
        """
        config = reload_config({"QDRANT_API_KEY": ""})
        assert config.qdrant_api_key is None

    def test_qdrant_api_key_preserved_when_set(self, reload_config):
        """Test that valid QDRANT_API_KEY is preserved."""
        config = reload_config({"QDRANT_API_KEY": "real-api-key"})
        assert config.qdrant_api_key == "real-api-key"

    def test_rag_settings_defaults(self, reload_config):
        """Test RAG settings have correct defaults."""
        config = reload_config({})
        assert config.top_k == 5
        assert config.min_score == 0.3

    def test_voyage_settings_defaults(self, reload_config):
        """Test Voyage AI settings have correct defaults."""
        config = reload_config({})
        assert config.voyage_model_docs == "voyage-4-large"
        assert config.voyage_model_queries == "voyage-4-lite"
        assert config.voyage_model_rerank == "rerank-2.5"
        assert config.voyage_embedding_dim == 1024

    def test_voyage_embedding_dim_from_env(self, reload_config):
        """Test voyage embedding dimension parsed from environment."""
        config = reload_config({"VOYAGE_EMBEDDING_DIM": "512"})
        assert config.voyage_embedding_dim == 512

    def test_search_configuration_defaults(self, reload_config):
        """Test search configuration defaults."""
        config = reload_config({})
        assert config.search_top_k == 20
        assert config.rerank_top_k == 3

    def test_search_configuration_from_env(self, reload_config):
        """Test search configuration loaded from environment."""
        config = reload_config({"SEARCH_TOP_K": "50", "RERANK_TOP_K": "10"})
        assert config.search_top_k == 50
        assert config.rerank_top_k == 10

    def test_cesc_configuration_defaults(self, reload_config):
        """Test CESC configuration defaults."""
        config = reload_config({})
        assert config.cesc_enabled is True
        assert config.cesc_extraction_frequency == 3
        assert config.user_context_ttl == 30 * 24 * 3600  # 30 days

    def test_cesc_disabled_from_env(self, reload_config):
        """Test CESC can be disabled via environment."""
        config = reload_config({"CESC_ENABLED": "false"})
        assert config.cesc_enabled is False

    def test_hybrid_search_weights_defaults(self, reload_config):
        """Test hybrid search weight defaults."""
        config = reload_config({})
        assert config.hybrid_dense_weight == 0.6
        assert config.hybrid_sparse_weight == 0.4

    def test_hybrid_search_weights_from_env(self, reload_config):
        """Test hybrid search weights from environment."""
        config = reload_config({"HYBRID_DENSE_WEIGHT": "0.8", "HYBRID_SPARSE_WEIGHT": "0.2"})
        assert config.hybrid_dense_weight == 0.8
        assert config.hybrid_sparse_weight == 0.2

    def test_freshness_boost_disabled_by_default(self, reload_config):
        """Test freshness boost disabled by default."""
        config = reload_config({})
        assert config.freshness_boost_enabled is False
        assert config.freshness_field == "created_at"
        assert config.freshness_scale_days == 30

    def test_freshness_boost_enabled_from_env(self, reload_config):
        """Test freshness boost enabled from environment."""
        config = reload_config({"FRESHNESS_BOOST": "true", "FRESHNESS_SCALE_DAYS": "7"})
        assert config.freshness_boost_enabled is True
        assert config.freshness_scale_days == 7

    def test_mmr_disabled_by_default(self, reload_config):
        """Test MMR diversity disabled by default."""
        config = reload_config({})
        assert config.mmr_enabled is False
        assert config.mmr_lambda == 0.7

    def test_mmr_enabled_from_env(self, reload_config):
        """Test MMR can be enabled via environment."""
        config = reload_config({"MMR_ENABLED": "true", "MMR_LAMBDA": "0.5"})
        assert config.mmr_enabled is True
        assert config.mmr_lambda == 0.5

    def test_qdrant_quantization_enabled_by_default(self, reload_config):
        """Test Qdrant quantization enabled by default."""
        config = reload_config({})
        assert config.qdrant_use_quantization is True
        assert config.qdrant_quantization_rescore is True
        assert config.qdrant_quantization_oversampling == 2.0
        assert config.qdrant_quantization_always_ram is True

    def test_qdrant_quantization_disabled_from_env(self, reload_config):
        """Test Qdrant quantization can be disabled via environment."""
        env = {
            "QDRANT_USE_QUANTIZATION": "false",
            "QDRANT_QUANTIZATION_RESCORE": "false",
            "QDRANT_QUANTIZATION_OVERSAMPLING": "1.5",
            "QDRANT_QUANTIZATION_ALWAYS_RAM": "false",
        }
        config = reload_config(env)
        assert config.qdrant_use_quantization is False
        assert config.qdrant_quantization_rescore is False
        assert config.qdrant_quantization_oversampling == 1.5
        assert config.qdrant_quantization_always_ram is False

    def test_llm_api_key_fallback_to_openai(self, reload_config):
        """Test LLM API key falls back to OPENAI_API_KEY."""
        config = reload_config({"OPENAI_API_KEY": "openai-fallback-key"})
        assert config.llm_api_key == "openai-fallback-key"

    def test_llm_api_key_prefers_llm_key(self, reload_config):
        """Test LLM_API_KEY takes precedence over OPENAI_API_KEY."""
        config = reload_config({"LLM_API_KEY": "primary-key", "OPENAI_API_KEY": "fallback-key"})
        assert config.llm_api_key == "primary-key"

    def test_legacy_voyage_settings(self, reload_config):
        """Test legacy voyage settings for backward compatibility."""
        config = reload_config({})
        assert config.voyage_embed_model == "voyage-3-large"
        assert config.voyage_cache_model == "voyage-3-lite"
        assert config.voyage_rerank_model == "rerank-2"

    def test_bm42_url_default(self, reload_config):
        """Test BM42 sparse embedding service URL default."""
        config = reload_config({})
        assert config.bm42_url == "http://localhost:8002"

    def test_bm42_url_from_env(self, reload_config):
        """Test BM42 URL from environment."""
        config = reload_config({"BM42_URL": "http://bm42:8002"})
        assert config.bm42_url == "http://bm42:8002"


class TestBotConfigDataclass:
    """Tests for BotConfig as a dataclass."""

    def test_config_is_dataclass(self):
        """Test that BotConfig is a dataclass."""
        from dataclasses import is_dataclass

        from telegram_bot.config import BotConfig

        assert is_dataclass(BotConfig)

    def test_config_can_be_instantiated_with_overrides(self):
        """Test that config values can be overridden at instantiation."""
        from telegram_bot.config import BotConfig

        config = BotConfig(
            telegram_token="override-token",
            top_k=10,
            min_score=0.5,
        )

        assert config.telegram_token == "override-token"
        assert config.top_k == 10
        assert config.min_score == 0.5

    def test_config_repr(self):
        """Test that config has a string representation."""
        from telegram_bot.config import BotConfig

        config = BotConfig()
        repr_str = repr(config)

        assert "BotConfig" in repr_str
        assert "telegram_token" in repr_str
