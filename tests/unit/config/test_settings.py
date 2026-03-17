"""Comprehensive unit tests for Settings configuration class."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.config.constants import (
    DEFAULT_COLLECTION,
    DEFAULTS,
    APIProvider,
    BatchSizes,
    ModelName,
    RetrievalStages,
    SearchEngine,
)
from src.config.settings import Settings


# Fixture to prevent load_dotenv from loading real .env file
@pytest.fixture(autouse=True)
def mock_load_dotenv():
    """Prevent load_dotenv from loading real .env file during tests."""
    with patch("src.config.settings.load_dotenv"):
        yield


class TestSettingsInit:
    """Test Settings initialization and loading from environment."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-anthropic-key"}, clear=True)
    def test_init_with_default_provider_claude(self):
        """Test initialization with default provider (Claude) and valid API key."""
        settings = Settings()

        assert settings.api_provider == APIProvider.CLAUDE
        assert settings.anthropic_api_key == "test-anthropic-key"

    @patch.dict(
        os.environ,
        {
            "API_PROVIDER": "openai",
            "OPENAI_API_KEY": "test-openai-key",
        },
        clear=True,
    )
    def test_init_with_openai_provider_from_env(self):
        """Test initialization loading API_PROVIDER from environment."""
        settings = Settings()

        assert settings.api_provider == APIProvider.OPENAI
        assert settings.openai_api_key == "test-openai-key"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_init_default_values(self):
        """Test that default values are correctly applied."""
        settings = Settings()

        # Model defaults
        assert settings.temperature == 0.0
        assert settings.max_tokens == 4096
        assert settings.max_retries == DEFAULTS["max_retries"]
        assert settings.retry_backoff == DEFAULTS["retry_backoff"]

        # Vector DB defaults
        assert settings.qdrant_url == "http://localhost:6333"
        assert settings.qdrant_api_key == ""

        # Search defaults
        assert settings.search_engine == SearchEngine.HYBRID_RRF_COLBERT
        assert settings.score_threshold == 0.3
        assert settings.top_k == 10

        # Collection default
        assert settings.collection_name == DEFAULT_COLLECTION

        # Batch sizes
        assert settings.batch_size_embeddings == BatchSizes.EMBEDDINGS
        assert settings.batch_size_documents == BatchSizes.DOCUMENTS
        assert settings.batch_size_queries == BatchSizes.QUERIES

        # Retrieval stages
        assert settings.retrieval_stage1_candidates == RetrievalStages.STAGE1_CANDIDATES
        assert settings.retrieval_stage2_final == RetrievalStages.STAGE2_FINAL

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_init_feature_flags_defaults(self):
        """Test feature flag default values."""
        settings = Settings()

        # Feature flags default to True
        assert settings.enable_caching is True
        assert settings.enable_query_expansion is True
        assert settings.enable_langfuse is True

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "test-key",
            "ENABLE_CACHING": "false",
            "ENABLE_QUERY_EXPANSION": "FALSE",
            "ENABLE_LANGFUSE": "false",
        },
        clear=True,
    )
    def test_init_feature_flags_from_env(self):
        """Test feature flags loaded from environment variables."""
        settings = Settings()

        assert settings.enable_caching is False
        assert settings.enable_query_expansion is False
        assert settings.enable_langfuse is False

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "test-key",
            "ENV": "production",
            "DEBUG": "true",
        },
        clear=True,
    )
    def test_init_environment_settings(self):
        """Test environment and debug settings from env vars."""
        settings = Settings()

        assert settings.env == "production"
        assert settings.debug is True

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_init_environment_defaults(self):
        """Test environment defaults when not set."""
        settings = Settings()

        assert settings.env == "development"
        assert settings.debug is False

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_init_constructor_overrides_env(self):
        """Test that constructor arguments override environment variables."""
        settings = Settings(
            temperature=0.7,
            max_tokens=2048,
            qdrant_url="https://custom-qdrant.example.com",
            score_threshold=0.5,
            top_k=20,
        )

        assert settings.temperature == 0.7
        assert settings.max_tokens == 2048
        assert settings.qdrant_url == "https://custom-qdrant.example.com"
        assert settings.score_threshold == 0.5
        assert settings.top_k == 20

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "env-key",
        },
        clear=True,
    )
    def test_init_constructor_api_key_override(self):
        """Test that constructor API keys override environment."""
        settings = Settings(anthropic_api_key="constructor-key")

        assert settings.anthropic_api_key == "constructor-key"

    @patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-key",
            "QDRANT_URL": "https://env-qdrant.example.com",
            "QDRANT_API_KEY": "qdrant-secret",
            "COLLECTION_NAME": "my_collection",
        },
        clear=True,
    )
    def test_init_vector_db_from_env(self):
        """Test vector database settings loaded from environment."""
        settings = Settings(api_provider="openai")

        assert settings.qdrant_url == "https://env-qdrant.example.com"
        assert settings.qdrant_api_key == "qdrant-secret"
        assert settings.collection_name == "my_collection"

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "test-key",
            "SEARCH_ENGINE": "baseline",
        },
        clear=True,
    )
    def test_init_search_engine_from_env(self):
        """Test search engine selection from environment."""
        settings = Settings()

        assert settings.search_engine == SearchEngine.BASELINE

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_init_paths_defaults(self):
        """Test that path defaults are relative to project root."""
        settings = Settings()

        # Paths should be Path objects
        assert isinstance(settings.data_dir, Path)
        assert isinstance(settings.docs_dir, Path)
        assert isinstance(settings.logs_dir, Path)
        assert isinstance(settings.project_root, Path)

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "test-key",
            "DATA_DIR": "/custom/data",
            "DOCS_DIR": "/custom/docs",
            "LOGS_DIR": "/custom/logs",
        },
        clear=True,
    )
    @patch("pathlib.Path.mkdir")
    def test_init_paths_from_env(self, mock_mkdir):
        """Test custom paths from environment variables."""
        settings = Settings()

        assert settings.data_dir == Path("/custom/data")
        assert settings.docs_dir == Path("/custom/docs")
        assert settings.logs_dir == Path("/custom/logs")
        # Verify mkdir was called for logs_dir
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    @patch("pathlib.Path.mkdir")
    def test_init_paths_from_constructor(self, mock_mkdir):
        """Test custom paths from constructor arguments."""
        settings = Settings(
            data_dir="/arg/data",
            docs_dir="/arg/docs",
            logs_dir="/arg/logs",
        )

        assert settings.data_dir == Path("/arg/data")
        assert settings.docs_dir == Path("/arg/docs")
        assert settings.logs_dir == Path("/arg/logs")
        # Verify mkdir was called for logs_dir
        mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)


class TestSettingsValidation:
    """Test API key validation for different providers."""

    @patch.dict(os.environ, {}, clear=True)
    def test_validation_missing_anthropic_key_raises(self):
        """Test that missing Anthropic API key raises ValueError for Claude provider."""
        with pytest.raises(ValueError) as exc_info:
            Settings(api_provider="claude")

        assert "ANTHROPIC_API_KEY not set" in str(exc_info.value)
        assert "API_PROVIDER=claude" in str(exc_info.value)

    @patch.dict(os.environ, {}, clear=True)
    def test_validation_missing_openai_key_raises(self):
        """Test that missing OpenAI API key raises ValueError for OpenAI provider."""
        with pytest.raises(ValueError) as exc_info:
            Settings(api_provider="openai")

        assert "OPENAI_API_KEY not set" in str(exc_info.value)
        assert "API_PROVIDER=openai" in str(exc_info.value)

    @patch.dict(os.environ, {}, clear=True)
    def test_validation_missing_groq_key_raises(self):
        """Test that missing Groq API key raises ValueError for Groq provider."""
        with pytest.raises(ValueError) as exc_info:
            Settings(api_provider="groq")

        assert "GROQ_API_KEY not set" in str(exc_info.value)
        assert "API_PROVIDER=groq" in str(exc_info.value)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "valid-key"}, clear=True)
    def test_validation_valid_anthropic_key_passes(self):
        """Test that valid Anthropic API key passes validation."""
        settings = Settings(api_provider="claude")

        assert settings.api_provider == APIProvider.CLAUDE
        assert settings.anthropic_api_key == "valid-key"

    @patch.dict(os.environ, {"OPENAI_API_KEY": "valid-key"}, clear=True)
    def test_validation_valid_openai_key_passes(self):
        """Test that valid OpenAI API key passes validation."""
        settings = Settings(api_provider="openai")

        assert settings.api_provider == APIProvider.OPENAI
        assert settings.openai_api_key == "valid-key"

    @patch.dict(os.environ, {"GROQ_API_KEY": "valid-key"}, clear=True)
    def test_validation_valid_groq_key_passes(self):
        """Test that valid Groq API key passes validation."""
        settings = Settings(api_provider="groq")

        assert settings.api_provider == APIProvider.GROQ
        assert settings.groq_api_key == "valid-key"

    @patch.dict(os.environ, {}, clear=True)
    def test_validation_constructor_key_passes(self):
        """Test that providing API key via constructor passes validation."""
        settings = Settings(api_provider="openai", openai_api_key="constructor-key")

        assert settings.api_provider == APIProvider.OPENAI
        assert settings.openai_api_key == "constructor-key"

    @patch.dict(
        os.environ,
        {
            "API_PROVIDER": "claude",
            "ANTHROPIC_API_KEY": "",  # Empty string
        },
        clear=True,
    )
    def test_validation_empty_string_key_raises(self):
        """Test that empty string API key raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            Settings()

        assert "ANTHROPIC_API_KEY not set" in str(exc_info.value)

    @patch.dict(os.environ, {}, clear=True)
    def test_validation_zai_provider_no_validation(self):
        """Test that Z_AI provider does not require validation (legacy)."""
        # Z_AI provider should work without API key validation
        settings = Settings(api_provider="zai")

        assert settings.api_provider == APIProvider.Z_AI


class TestSettingsToDict:
    """Test to_dict method and sensitive data exclusion."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret-key-123"}, clear=True)
    def test_to_dict_returns_dict(self):
        """Test that to_dict returns a dictionary."""
        settings = Settings()
        result = settings.to_dict()

        assert isinstance(result, dict)

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret-key-123"}, clear=True)
    def test_to_dict_excludes_api_keys(self):
        """Test that to_dict excludes sensitive API keys."""
        settings = Settings()
        result = settings.to_dict()

        # Should not contain API keys
        assert "anthropic_api_key" not in result
        assert "openai_api_key" not in result
        assert "groq_api_key" not in result
        assert "qdrant_api_key" not in result

        # Should not contain the actual secret value
        assert "secret-key-123" not in str(result.values())

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret-key-123"}, clear=True)
    def test_to_dict_contains_expected_keys(self):
        """Test that to_dict contains all expected configuration keys."""
        settings = Settings()
        result = settings.to_dict()

        expected_keys = {
            "api_provider",
            "model_name",
            "temperature",
            "max_tokens",
            "qdrant_url",
            "collection_name",
            "search_engine",
            "score_threshold",
            "top_k",
            "batch_size_embeddings",
            "batch_size_documents",
            "enable_caching",
            "enable_query_expansion",
            "enable_langfuse",
            "quantization_mode",
            "quantization_rescore",
            "quantization_oversampling",
            "small_to_big_mode",
            "small_to_big_window_before",
            "small_to_big_window_after",
            "max_expanded_chunks",
            "max_context_tokens",
            "acorn_mode",
            "acorn_max_selectivity",
            "acorn_enabled_selectivity_threshold",
            "use_hyde",
            "hyde_min_words",
            "use_contextualized_embeddings",
            "contextualized_embedding_dim",
            "env",
            "debug",
        }

        assert set(result.keys()) == expected_keys

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "secret-key-123"}, clear=True)
    def test_to_dict_enum_values_are_strings(self):
        """Test that enum values in to_dict are converted to strings."""
        settings = Settings()
        result = settings.to_dict()

        # Enum values should be strings, not enum objects
        assert isinstance(result["api_provider"], str)
        assert isinstance(result["search_engine"], str)
        assert result["api_provider"] == "claude"
        assert result["search_engine"] == "hybrid_rrf_colbert"

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "secret",
            "ENABLE_CACHING": "false",
            "DEBUG": "true",
        },
        clear=True,
    )
    def test_to_dict_values_match_settings(self):
        """Test that to_dict values match the actual settings attributes."""
        settings = Settings(
            temperature=0.5,
            top_k=15,
        )
        result = settings.to_dict()

        assert result["temperature"] == 0.5
        assert result["top_k"] == 15
        assert result["enable_caching"] is False
        assert result["debug"] is True
        assert result["qdrant_url"] == settings.qdrant_url
        assert result["collection_name"] == settings.collection_name


class TestSettingsDefaultModel:
    """Test default model selection per provider."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_default_model_claude(self):
        """Test default model for Claude provider."""
        settings = Settings(api_provider="claude")

        assert settings.model_name == ModelName.CLAUDE_SONNET.value

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=True)
    def test_default_model_openai(self):
        """Test default model for OpenAI provider."""
        settings = Settings(api_provider="openai")

        assert settings.model_name == ModelName.GPT_4_TURBO.value

    @patch.dict(os.environ, {"GROQ_API_KEY": "test-key"}, clear=True)
    def test_default_model_groq(self):
        """Test default model for Groq provider."""
        settings = Settings(api_provider="groq")

        assert settings.model_name == ModelName.GROQ_LLAMA3_70B.value

    @patch.dict(os.environ, {}, clear=True)
    def test_default_model_zai(self):
        """Test default model for Z_AI provider (legacy)."""
        settings = Settings(api_provider="zai")

        assert settings.model_name == "glm-4.6"

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_custom_model_overrides_default(self):
        """Test that custom model_name overrides the provider default."""
        settings = Settings(
            api_provider="claude",
            model_name="claude-3-opus-20240229",
        )

        assert settings.model_name == "claude-3-opus-20240229"

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "test-key",
            "MODEL_NAME": "custom-model-from-env",
        },
        clear=True,
    )
    def test_model_from_env_overrides_default(self):
        """Test that MODEL_NAME from env overrides provider default."""
        settings = Settings(api_provider="claude")

        assert settings.model_name == "custom-model-from-env"

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "test-key",
            "MODEL_NAME": "env-model",
        },
        clear=True,
    )
    def test_constructor_model_overrides_env(self):
        """Test that constructor model_name overrides env MODEL_NAME."""
        settings = Settings(
            api_provider="claude",
            model_name="constructor-model",
        )

        assert settings.model_name == "constructor-model"

    def test_default_model_for_provider_static_method(self):
        """Test the static _default_model_for_provider method directly."""
        assert (
            Settings._default_model_for_provider(APIProvider.CLAUDE)
            == ModelName.CLAUDE_SONNET.value
        )
        assert (
            Settings._default_model_for_provider(APIProvider.OPENAI) == ModelName.GPT_4_TURBO.value
        )
        assert (
            Settings._default_model_for_provider(APIProvider.GROQ)
            == ModelName.GROQ_LLAMA3_70B.value
        )
        assert Settings._default_model_for_provider(APIProvider.Z_AI) == "glm-4.6"


class TestSettingsRepr:
    """Test string representation of Settings."""

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_repr_contains_key_info(self):
        """Test that __repr__ contains essential configuration info."""
        settings = Settings()
        repr_str = repr(settings)

        assert "Settings(" in repr_str
        assert "api_provider=claude" in repr_str
        assert "model=" in repr_str
        assert "search_engine=" in repr_str
        assert "qdrant_url=" in repr_str
        assert "collection=" in repr_str
        assert "env=" in repr_str

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "super-secret-key"}, clear=True)
    def test_repr_does_not_contain_secrets(self):
        """Test that __repr__ does not expose API keys."""
        settings = Settings()
        repr_str = repr(settings)

        assert "super-secret-key" not in repr_str
        assert "api_key" not in repr_str.lower()


class TestSettingsEdgeCases:
    """Test edge cases and special scenarios."""

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "test-key",
            "TEMPERATURE": "0.9",  # Note: temperature comes from constructor only
        },
        clear=True,
    )
    def test_temperature_zero_is_valid(self):
        """Test that temperature=0 is preserved (not treated as falsy)."""
        settings = Settings(temperature=0.0)

        assert settings.temperature == 0.0

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_batch_sizes_from_constructor(self):
        """Test batch size overrides from constructor."""
        settings = Settings(
            batch_size_embeddings=64,
            batch_size_documents=32,
        )

        assert settings.batch_size_embeddings == 64
        assert settings.batch_size_documents == 32

    @patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-key",
            "API_PROVIDER": "openai",
        },
        clear=True,
    )
    def test_all_providers_have_different_defaults(self):
        """Test that each provider has a distinct default model."""
        # Create settings for each provider and verify unique defaults
        openai_settings = Settings()

        with patch.dict(
            os.environ, {"GROQ_API_KEY": "test-key", "API_PROVIDER": "groq"}, clear=True
        ):
            groq_settings = Settings()

        with patch.dict(
            os.environ, {"ANTHROPIC_API_KEY": "test-key", "API_PROVIDER": "claude"}, clear=True
        ):
            claude_settings = Settings()

        # All should have different model names
        assert openai_settings.model_name != groq_settings.model_name
        assert groq_settings.model_name != claude_settings.model_name
        assert claude_settings.model_name != openai_settings.model_name

    @patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}, clear=True)
    def test_search_engine_enum_values(self):
        """Test all search engine enum values can be set."""
        for engine in SearchEngine:
            settings = Settings(search_engine=engine.value)
            assert settings.search_engine == engine
