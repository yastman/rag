"""Unit tests for ACORN (Agnostic Contiguous Optimized Retrieval Network) support.

Tests cover:
- AcornMode enum values
- ACORN settings in Settings class
- ACORN search params construction in search engines
- Auto mode selectivity logic
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import models

from src.config.constants import AcornMode, QuantizationMode
from src.config.settings import Settings
from src.retrieval.search_engines import ACORN_AVAILABLE, BaselineSearchEngine


# Skip marker for tests requiring AcornSearchParams
requires_acorn = pytest.mark.skipif(
    not ACORN_AVAILABLE,
    reason="AcornSearchParams not available in current qdrant-client version",
)


class TestAcornModeEnum:
    """Test AcornMode enum values and behavior."""

    def test_acorn_mode_values(self):
        """Test that all expected AcornMode values exist."""
        assert AcornMode.OFF.value == "off"
        assert AcornMode.ON.value == "on"
        assert AcornMode.AUTO.value == "auto"

    def test_acorn_mode_from_string(self):
        """Test creating AcornMode from string values."""
        assert AcornMode("off") == AcornMode.OFF
        assert AcornMode("on") == AcornMode.ON
        assert AcornMode("auto") == AcornMode.AUTO

    def test_acorn_mode_invalid_value(self):
        """Test that invalid values raise ValueError."""
        with pytest.raises(ValueError):
            AcornMode("invalid")

    def test_acorn_mode_is_string_enum(self):
        """Test that AcornMode values can be used as strings."""
        assert str(AcornMode.OFF) == "off"
        assert AcornMode.ON.value == "on"


class TestAcornSettings:
    """Test ACORN configuration in Settings class."""

    def test_acorn_default_settings(self):
        """Test default ACORN settings values."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")

            assert settings.acorn_mode == AcornMode.OFF
            assert settings.acorn_max_selectivity == 0.4
            assert settings.acorn_enabled_selectivity_threshold == 0.4

    def test_acorn_mode_env_override(self):
        """Test ACORN_MODE environment variable override."""
        env_vars = {
            "OPENAI_API_KEY": "test-key",
            "ACORN_MODE": "auto",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings(api_provider="openai")

            assert settings.acorn_mode == AcornMode.AUTO

    def test_acorn_max_selectivity_env_override(self):
        """Test ACORN_MAX_SELECTIVITY environment variable override."""
        env_vars = {
            "OPENAI_API_KEY": "test-key",
            "ACORN_MAX_SELECTIVITY": "0.6",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings(api_provider="openai")

            assert settings.acorn_max_selectivity == 0.6

    def test_acorn_enabled_selectivity_threshold_env_override(self):
        """Test ACORN_ENABLED_SELECTIVITY_THRESHOLD environment variable override."""
        env_vars = {
            "OPENAI_API_KEY": "test-key",
            "ACORN_ENABLED_SELECTIVITY_THRESHOLD": "0.3",
        }
        with patch.dict(os.environ, env_vars, clear=False):
            settings = Settings(api_provider="openai")

            assert settings.acorn_enabled_selectivity_threshold == 0.3

    def test_acorn_settings_in_to_dict(self):
        """Test that ACORN settings appear in to_dict() output."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            settings_dict = settings.to_dict()

            assert "acorn_mode" in settings_dict
            assert "acorn_max_selectivity" in settings_dict
            assert "acorn_enabled_selectivity_threshold" in settings_dict
            assert settings_dict["acorn_mode"] == "off"


class TestAcornShouldUseLogic:
    """Test _should_use_acorn() method logic in BaseSearchEngine."""

    @pytest.fixture
    def mock_settings_acorn_off(self):
        """Create settings with ACORN mode OFF."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            settings.acorn_mode = AcornMode.OFF
            return settings

    @pytest.fixture
    def mock_settings_acorn_on(self):
        """Create settings with ACORN mode ON."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            settings.acorn_mode = AcornMode.ON
            return settings

    @pytest.fixture
    def mock_settings_acorn_auto(self):
        """Create settings with ACORN mode AUTO."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            settings.acorn_mode = AcornMode.AUTO
            settings.acorn_enabled_selectivity_threshold = 0.4
            return settings

    def test_acorn_off_never_enables(self, mock_settings_acorn_off):
        """Test that ACORN OFF mode never enables ACORN."""
        with patch.object(BaselineSearchEngine, "__init__", lambda _self, _settings: None):
            engine = BaselineSearchEngine(mock_settings_acorn_off)
            engine.settings = mock_settings_acorn_off

            # No filters
            assert engine._should_use_acorn(has_filters=False, estimated_selectivity=None) is False
            # With filters
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=None) is False
            # Low selectivity
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=0.1) is False

    def test_acorn_on_enables_with_filters(self, mock_settings_acorn_on):
        """Test that ACORN ON mode enables when filters are present."""
        with patch.object(BaselineSearchEngine, "__init__", lambda _self, _settings: None):
            engine = BaselineSearchEngine(mock_settings_acorn_on)
            engine.settings = mock_settings_acorn_on

            # With filters - should enable
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=None) is True
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=0.9) is True

            # Without filters - should not enable
            assert engine._should_use_acorn(has_filters=False, estimated_selectivity=None) is False

    def test_acorn_auto_selectivity_logic(self, mock_settings_acorn_auto):
        """Test that ACORN AUTO mode uses selectivity threshold."""
        with patch.object(BaselineSearchEngine, "__init__", lambda _self, _settings: None):
            engine = BaselineSearchEngine(mock_settings_acorn_auto)
            engine.settings = mock_settings_acorn_auto

            # No filters - never enable
            assert engine._should_use_acorn(has_filters=False, estimated_selectivity=0.1) is False

            # Low selectivity - should enable
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=0.1) is True
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=0.3) is True

            # High selectivity - should not enable
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=0.5) is False
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=0.9) is False

            # Exactly at threshold - should not enable (< not <=)
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=0.4) is False

    def test_acorn_auto_unknown_selectivity_enables(self, mock_settings_acorn_auto):
        """Test that ACORN AUTO with unknown selectivity defaults to enabled."""
        with patch.object(BaselineSearchEngine, "__init__", lambda _self, _settings: None):
            engine = BaselineSearchEngine(mock_settings_acorn_auto)
            engine.settings = mock_settings_acorn_auto

            # Unknown selectivity with filters - conservative default to enabled
            assert engine._should_use_acorn(has_filters=True, estimated_selectivity=None) is True


class TestBuildSearchParams:
    """Test _build_search_params() method in BaseSearchEngine."""

    @pytest.fixture
    def mock_settings(self):
        """Create settings for testing."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            settings.quantization_mode = QuantizationMode.BINARY
            settings.quantization_rescore = True
            settings.quantization_oversampling = 2.0
            settings.acorn_mode = AcornMode.ON
            settings.acorn_max_selectivity = 0.4
            return settings

    @requires_acorn
    def test_build_search_params_with_acorn(self, mock_settings):
        """Test that search params include ACORN when enabled."""
        with patch.object(BaselineSearchEngine, "__init__", lambda _self, _settings: None):
            engine = BaselineSearchEngine(mock_settings)
            engine.settings = mock_settings

            params = engine._build_search_params(has_filters=True, estimated_selectivity=0.2)

            assert params.acorn is not None
            assert params.acorn.enable is True
            assert params.acorn.max_selectivity == 0.4

    @requires_acorn
    def test_build_search_params_without_acorn(self, mock_settings):
        """Test that search params exclude ACORN when disabled."""
        mock_settings.acorn_mode = AcornMode.OFF
        with patch.object(BaselineSearchEngine, "__init__", lambda _self, _settings: None):
            engine = BaselineSearchEngine(mock_settings)
            engine.settings = mock_settings

            params = engine._build_search_params(has_filters=True, estimated_selectivity=0.2)

            assert params.acorn is None

    def test_build_search_params_includes_quantization(self, mock_settings):
        """Test that search params always include quantization settings."""
        with patch.object(BaselineSearchEngine, "__init__", lambda _self, _settings: None):
            engine = BaselineSearchEngine(mock_settings)
            engine.settings = mock_settings

            params = engine._build_search_params(has_filters=False, estimated_selectivity=None)

            assert params.quantization is not None
            assert params.quantization.rescore is True
            assert params.quantization.oversampling == 2.0


class TestBaselineSearchEngineAcorn:
    """Test ACORN integration in BaselineSearchEngine.search()."""

    @pytest.fixture
    def mock_qdrant_client(self):
        """Create a mock Qdrant client."""
        client = MagicMock()
        client.search.return_value = [
            MagicMock(
                payload={"metadata": {"article_number": "1"}, "page_content": "Test content"},
                score=0.95,
            )
        ]
        return client

    @pytest.fixture
    def mock_settings_acorn_on(self):
        """Create settings with ACORN mode ON."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            settings = Settings(api_provider="openai")
            settings.acorn_mode = AcornMode.ON
            settings.acorn_max_selectivity = 0.4
            settings.quantization_mode = QuantizationMode.OFF
            return settings

    @requires_acorn
    def test_search_with_filter_enables_acorn(self, mock_qdrant_client, mock_settings_acorn_on):
        """Test that search with filter enables ACORN in search params."""
        with patch("src.retrieval.search_engines.QdrantClient", return_value=mock_qdrant_client):
            engine = BaselineSearchEngine(mock_settings_acorn_on)
            engine.client = mock_qdrant_client

            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="city",
                        match=models.MatchValue(value="Sofia"),
                    )
                ]
            )

            engine.search(
                query_embedding=[0.1] * 1024,
                top_k=10,
                query_filter=query_filter,
                estimated_selectivity=0.2,
            )

            # Verify search was called with ACORN params
            call_kwargs = mock_qdrant_client.search.call_args.kwargs
            search_params = call_kwargs.get("search_params")

            assert search_params is not None
            assert search_params.acorn is not None
            assert search_params.acorn.enable is True

    @requires_acorn
    def test_search_without_filter_no_acorn(self, mock_qdrant_client, mock_settings_acorn_on):
        """Test that search without filter does not enable ACORN."""
        with patch("src.retrieval.search_engines.QdrantClient", return_value=mock_qdrant_client):
            engine = BaselineSearchEngine(mock_settings_acorn_on)
            engine.client = mock_qdrant_client

            engine.search(
                query_embedding=[0.1] * 1024,
                top_k=10,
                query_filter=None,
                estimated_selectivity=None,
            )

            # Verify search was called without ACORN params
            call_kwargs = mock_qdrant_client.search.call_args.kwargs
            search_params = call_kwargs.get("search_params")

            # ACORN should be None when no filters
            assert search_params.acorn is None


@requires_acorn
class TestAcornSearchParamsModel:
    """Test that qdrant-client supports AcornSearchParams model."""

    def test_acorn_search_params_exists(self):
        """Test that AcornSearchParams exists in qdrant_client.models."""
        assert hasattr(models, "AcornSearchParams")

    def test_acorn_search_params_create(self):
        """Test creating AcornSearchParams with expected fields."""
        params = models.AcornSearchParams(enable=True, max_selectivity=0.4)

        assert params.enable is True
        assert params.max_selectivity == 0.4

    def test_acorn_search_params_in_search_params(self):
        """Test that AcornSearchParams can be nested in SearchParams."""
        acorn = models.AcornSearchParams(enable=True, max_selectivity=0.3)
        search_params = models.SearchParams(acorn=acorn)

        assert search_params.acorn is not None
        assert search_params.acorn.enable is True
        assert search_params.acorn.max_selectivity == 0.3

    def test_acorn_search_params_defaults(self):
        """Test AcornSearchParams default values."""
        params = models.AcornSearchParams()

        # Default is enable=False per Qdrant docs
        assert params.enable is False
        assert params.max_selectivity is None
