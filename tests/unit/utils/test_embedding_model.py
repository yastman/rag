"""Unit tests for the BGE-M3 embedding model singleton pattern.

Tests verify that:
1. Singleton pattern works correctly (same instance returned)
2. Initialization parameters are passed correctly
3. Models have expected attributes after initialization
4. clear_models() properly resets state
5. Edge cases are handled properly
"""

from unittest.mock import MagicMock, patch

import pytest


class TestGetBgeM3Model:
    """Tests for get_bge_m3_model() singleton function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton state before and after each test."""
        # Import here to access the module-level variables
        import src.models.embedding_model as embedding_module

        # Clear before test
        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None
        yield
        # Clear after test
        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_singleton_returns_same_instance(self, mock_model_class):
        """Test that get_bge_m3_model returns the same instance on multiple calls."""
        from src.models.embedding_model import get_bge_m3_model

        # Setup mock
        mock_instance = MagicMock()
        mock_model_class.return_value = mock_instance

        # First call - should create instance
        model1 = get_bge_m3_model()
        # Second call - should return same instance
        model2 = get_bge_m3_model()
        # Third call - should return same instance
        model3 = get_bge_m3_model()

        # All should be the exact same object
        assert model1 is model2
        assert model2 is model3
        # Model class should only be instantiated once
        assert mock_model_class.call_count == 1

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_default_initialization_parameters(self, mock_model_class):
        """Test that default parameters are passed correctly to the model."""
        from src.models.embedding_model import get_bge_m3_model

        mock_instance = MagicMock()
        mock_model_class.return_value = mock_instance

        get_bge_m3_model()

        # Check default parameters
        mock_model_class.assert_called_once_with(
            "BAAI/bge-m3",
            use_fp16=True,
            device=None,
        )

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_custom_initialization_parameters(self, mock_model_class):
        """Test that custom parameters are passed correctly to the model."""
        from src.models.embedding_model import get_bge_m3_model

        mock_instance = MagicMock()
        mock_model_class.return_value = mock_instance

        get_bge_m3_model(use_fp16=False, device="cuda")

        mock_model_class.assert_called_once_with(
            "BAAI/bge-m3",
            use_fp16=False,
            device="cuda",
        )

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_subsequent_calls_ignore_parameters(self, mock_model_class):
        """Test that parameters on subsequent calls are ignored (singleton already created)."""
        from src.models.embedding_model import get_bge_m3_model

        mock_instance = MagicMock()
        mock_model_class.return_value = mock_instance

        # First call with default params
        model1 = get_bge_m3_model(use_fp16=True, device="cpu")

        # Second call with different params - should be ignored
        model2 = get_bge_m3_model(use_fp16=False, device="cuda")

        # Should still be the same instance
        assert model1 is model2
        # Model should only be created once with first call's params
        mock_model_class.assert_called_once_with(
            "BAAI/bge-m3",
            use_fp16=True,
            device="cpu",
        )

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_returns_bgem3flagmodel_instance(self, mock_model_class):
        """Test that the returned object is the BGEM3FlagModel mock."""
        from src.models.embedding_model import get_bge_m3_model

        mock_instance = MagicMock()
        mock_instance.some_attribute = "test_value"
        mock_model_class.return_value = mock_instance

        model = get_bge_m3_model()

        assert model is mock_instance
        assert model.some_attribute == "test_value"


class TestGetSentenceTransformer:
    """Tests for get_sentence_transformer() singleton function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton state before and after each test."""
        import src.models.embedding_model as embedding_module

        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None
        yield
        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None

    @patch("src.models.embedding_model.SentenceTransformer")
    def test_singleton_returns_same_instance(self, mock_st_class):
        """Test that get_sentence_transformer returns the same instance on multiple calls."""
        from src.models.embedding_model import get_sentence_transformer

        mock_instance = MagicMock()
        mock_st_class.return_value = mock_instance

        # Multiple calls should return same instance
        st1 = get_sentence_transformer()
        st2 = get_sentence_transformer()
        st3 = get_sentence_transformer()

        assert st1 is st2
        assert st2 is st3
        assert mock_st_class.call_count == 1

    @patch("src.models.embedding_model.SentenceTransformer")
    def test_default_model_name(self, mock_st_class):
        """Test that default model name is BAAI/bge-m3."""
        from src.models.embedding_model import get_sentence_transformer

        mock_instance = MagicMock()
        mock_st_class.return_value = mock_instance

        get_sentence_transformer()

        mock_st_class.assert_called_once_with("BAAI/bge-m3")

    @patch("src.models.embedding_model.SentenceTransformer")
    def test_custom_model_name(self, mock_st_class):
        """Test that custom model name is used on first call."""
        from src.models.embedding_model import get_sentence_transformer

        mock_instance = MagicMock()
        mock_st_class.return_value = mock_instance

        get_sentence_transformer(model_name="sentence-transformers/all-MiniLM-L6-v2")

        mock_st_class.assert_called_once_with("sentence-transformers/all-MiniLM-L6-v2")

    @patch("src.models.embedding_model.SentenceTransformer")
    def test_subsequent_calls_ignore_model_name(self, mock_st_class):
        """Test that model_name on subsequent calls is ignored."""
        from src.models.embedding_model import get_sentence_transformer

        mock_instance = MagicMock()
        mock_st_class.return_value = mock_instance

        st1 = get_sentence_transformer(model_name="model-a")
        st2 = get_sentence_transformer(model_name="model-b")

        assert st1 is st2
        mock_st_class.assert_called_once_with("model-a")


class TestClearModels:
    """Tests for clear_models() utility function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton state before and after each test."""
        import src.models.embedding_model as embedding_module

        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None
        yield
        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None

    @patch("src.models.embedding_model.BGEM3FlagModel")
    @patch("src.models.embedding_model.SentenceTransformer")
    def test_clear_models_resets_bge_m3(self, mock_st_class, mock_bge_class):
        """Test that clear_models() clears the BGE-M3 singleton."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import clear_models, get_bge_m3_model

        mock_bge_class.return_value = MagicMock()
        mock_st_class.return_value = MagicMock()

        # Create instance
        get_bge_m3_model()
        assert embedding_module._bge_m3_model is not None

        # Clear
        with patch("gc.collect", return_value=0):
            clear_models()
        assert embedding_module._bge_m3_model is None

    @patch("src.models.embedding_model.BGEM3FlagModel")
    @patch("src.models.embedding_model.SentenceTransformer")
    def test_clear_models_resets_sentence_transformer(self, mock_st_class, mock_bge_class):
        """Test that clear_models() clears the SentenceTransformer singleton."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import clear_models, get_sentence_transformer

        mock_bge_class.return_value = MagicMock()
        mock_st_class.return_value = MagicMock()

        # Create instance
        get_sentence_transformer()
        assert embedding_module._sentence_transformer is not None

        # Clear
        with patch("gc.collect", return_value=0):
            clear_models()
        assert embedding_module._sentence_transformer is None

    @patch("src.models.embedding_model.BGEM3FlagModel")
    @patch("src.models.embedding_model.SentenceTransformer")
    def test_clear_models_allows_new_initialization(self, mock_st_class, mock_bge_class):
        """Test that after clear_models(), new instances can be created."""
        from src.models.embedding_model import clear_models, get_bge_m3_model

        mock_instance_1 = MagicMock(name="instance1")
        mock_instance_2 = MagicMock(name="instance2")
        mock_bge_class.side_effect = [mock_instance_1, mock_instance_2]
        mock_st_class.return_value = MagicMock()

        # First initialization
        model1 = get_bge_m3_model()
        assert model1 is mock_instance_1

        # Clear
        with patch("gc.collect", return_value=0):
            clear_models()

        # Second initialization - should create new instance
        model2 = get_bge_m3_model()
        assert model2 is mock_instance_2
        assert model1 is not model2

        # Model class should be called twice
        assert mock_bge_class.call_count == 2

    @patch("src.models.embedding_model.BGEM3FlagModel")
    @patch("src.models.embedding_model.SentenceTransformer")
    def test_clear_models_calls_gc_collect(self, mock_st_class, mock_bge_class):
        """Test that clear_models() triggers garbage collection."""
        from src.models.embedding_model import clear_models, get_bge_m3_model

        mock_bge_class.return_value = MagicMock()
        mock_st_class.return_value = MagicMock()

        get_bge_m3_model()

        with patch("gc.collect") as mock_gc:
            clear_models()
            mock_gc.assert_called_once()

    def test_clear_models_when_no_models_loaded(self):
        """Test that clear_models() works safely when no models are loaded."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import clear_models

        # Ensure both are None
        assert embedding_module._bge_m3_model is None
        assert embedding_module._sentence_transformer is None

        # Should not raise any exception
        with patch("gc.collect", return_value=0):
            clear_models()

        # Should still be None
        assert embedding_module._bge_m3_model is None
        assert embedding_module._sentence_transformer is None


class TestSingletonIsolation:
    """Tests for isolation between the two singletons."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton state before and after each test."""
        import src.models.embedding_model as embedding_module

        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None
        yield
        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None

    @patch("src.models.embedding_model.BGEM3FlagModel")
    @patch("src.models.embedding_model.SentenceTransformer")
    def test_singletons_are_independent(self, mock_st_class, mock_bge_class):
        """Test that BGE-M3 and SentenceTransformer singletons are separate."""
        from src.models.embedding_model import get_bge_m3_model, get_sentence_transformer

        mock_bge_instance = MagicMock(name="bge_model")
        mock_st_instance = MagicMock(name="st_model")
        mock_bge_class.return_value = mock_bge_instance
        mock_st_class.return_value = mock_st_instance

        bge_model = get_bge_m3_model()
        st_model = get_sentence_transformer()

        assert bge_model is not st_model
        assert bge_model is mock_bge_instance
        assert st_model is mock_st_instance

    @patch("src.models.embedding_model.BGEM3FlagModel")
    @patch("src.models.embedding_model.SentenceTransformer")
    def test_clear_affects_both_singletons(self, mock_st_class, mock_bge_class):
        """Test that clear_models() clears both singletons at once."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import (
            clear_models,
            get_bge_m3_model,
            get_sentence_transformer,
        )

        mock_bge_class.return_value = MagicMock()
        mock_st_class.return_value = MagicMock()

        # Create both
        get_bge_m3_model()
        get_sentence_transformer()

        assert embedding_module._bge_m3_model is not None
        assert embedding_module._sentence_transformer is not None

        # Clear both
        with patch("gc.collect", return_value=0):
            clear_models()

        assert embedding_module._bge_m3_model is None
        assert embedding_module._sentence_transformer is None


class TestLogging:
    """Tests for logging behavior in the singleton functions."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton state before and after each test."""
        import src.models.embedding_model as embedding_module

        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None
        yield
        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None

    @patch("src.models.embedding_model.BGEM3FlagModel")
    @patch("src.models.embedding_model.logger")
    def test_logs_info_on_first_initialization(self, mock_logger, mock_model_class):
        """Test that info is logged on first model initialization."""
        from src.models.embedding_model import get_bge_m3_model

        mock_model_class.return_value = MagicMock()

        get_bge_m3_model()

        # Check that info was logged for loading and success
        assert mock_logger.info.call_count == 2
        # First call should be about loading
        first_call_args = mock_logger.info.call_args_list[0][0][0]
        assert "Loading BGE-M3 model" in first_call_args
        # Second call should be about success
        second_call_args = mock_logger.info.call_args_list[1][0][0]
        assert "loaded successfully" in second_call_args

    @patch("src.models.embedding_model.BGEM3FlagModel")
    @patch("src.models.embedding_model.logger")
    def test_logs_debug_on_subsequent_calls(self, mock_logger, mock_model_class):
        """Test that debug is logged on subsequent calls (existing instance)."""
        from src.models.embedding_model import get_bge_m3_model

        mock_model_class.return_value = MagicMock()

        # First call
        get_bge_m3_model()
        mock_logger.reset_mock()

        # Second call
        get_bge_m3_model()

        # Should log debug, not info
        mock_logger.debug.assert_called_once()
        assert "existing" in mock_logger.debug.call_args[0][0].lower()

    @patch("src.models.embedding_model.BGEM3FlagModel")
    @patch("src.models.embedding_model.SentenceTransformer")
    @patch("src.models.embedding_model.logger")
    def test_logs_info_on_clear(self, mock_logger, mock_st_class, mock_bge_class):
        """Test that info is logged when clearing models."""
        from src.models.embedding_model import clear_models, get_bge_m3_model

        mock_bge_class.return_value = MagicMock()
        mock_st_class.return_value = MagicMock()

        get_bge_m3_model()
        mock_logger.reset_mock()

        with patch("gc.collect", return_value=0):
            clear_models()

        # Should log clearing BGE-M3
        mock_logger.info.assert_called()
        clear_call_args = mock_logger.info.call_args[0][0]
        assert "Clearing" in clear_call_args


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton state before and after each test."""
        import src.models.embedding_model as embedding_module

        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None
        yield
        embedding_module._bge_m3_model = None
        embedding_module._sentence_transformer = None

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_model_initialization_error_propagates(self, mock_model_class):
        """Test that exceptions during model initialization are propagated."""
        from src.models.embedding_model import get_bge_m3_model

        mock_model_class.side_effect = RuntimeError("CUDA out of memory")

        with pytest.raises(RuntimeError, match="CUDA out of memory"):
            get_bge_m3_model()

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_singleton_state_after_failed_init(self, mock_model_class):
        """Test that singleton remains None after failed initialization."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import get_bge_m3_model

        mock_model_class.side_effect = RuntimeError("Model load failed")

        with pytest.raises(RuntimeError):
            get_bge_m3_model()

        # Singleton should still be None (not set to failed instance)
        assert embedding_module._bge_m3_model is None

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_retry_after_failed_initialization(self, mock_model_class):
        """Test that initialization can be retried after a failure."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import get_bge_m3_model

        mock_instance = MagicMock()
        # First call fails, second succeeds
        mock_model_class.side_effect = [RuntimeError("First fail"), mock_instance]

        # First call fails
        with pytest.raises(RuntimeError):
            get_bge_m3_model()

        assert embedding_module._bge_m3_model is None

        # Second call succeeds
        result = get_bge_m3_model()
        assert result is mock_instance
        assert embedding_module._bge_m3_model is mock_instance

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_device_parameter_none_is_auto(self, mock_model_class):
        """Test that device=None means auto-detection."""
        from src.models.embedding_model import get_bge_m3_model

        mock_model_class.return_value = MagicMock()

        get_bge_m3_model(device=None)

        # Should be called with device=None (auto)
        call_kwargs = mock_model_class.call_args[1]
        assert call_kwargs["device"] is None

    @patch("src.models.embedding_model.BGEM3FlagModel")
    def test_use_fp16_false(self, mock_model_class):
        """Test that use_fp16=False is passed correctly."""
        from src.models.embedding_model import get_bge_m3_model

        mock_model_class.return_value = MagicMock()

        get_bge_m3_model(use_fp16=False)

        call_kwargs = mock_model_class.call_args[1]
        assert call_kwargs["use_fp16"] is False

    @patch("src.models.embedding_model.SentenceTransformer")
    def test_empty_model_name_passed_through(self, mock_st_class):
        """Test that empty string model name is passed (may fail in real code)."""
        from src.models.embedding_model import get_sentence_transformer

        mock_st_class.return_value = MagicMock()

        # Empty string should still be passed through
        get_sentence_transformer(model_name="")

        mock_st_class.assert_called_once_with("")
