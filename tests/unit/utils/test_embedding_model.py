"""Unit tests for the BGE-M3 embedding model singleton pattern.

Tests verify that:
1. Singleton pattern works correctly (same instance returned)
2. Initialization parameters are passed correctly
3. Models have expected attributes after initialization
4. clear_models() properly resets state
5. Edge cases are handled properly

NOTE: FlagEmbedding and sentence_transformers are optional (ml-local extra).
Tests mock them via sys.modules to work without the actual packages.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset singleton state before and after each test."""
    import src.models.embedding_model as embedding_module

    embedding_module._bge_m3_model = None
    embedding_module._sentence_transformer = None
    yield
    embedding_module._bge_m3_model = None
    embedding_module._sentence_transformer = None


@pytest.fixture()
def mock_flag_embedding():
    """Mock FlagEmbedding module in sys.modules for lazy import."""
    mock_module = MagicMock()
    mock_cls = MagicMock()
    mock_module.BGEM3FlagModel = mock_cls
    with patch.dict(sys.modules, {"FlagEmbedding": mock_module}):
        yield mock_cls


@pytest.fixture()
def mock_sentence_transformers():
    """Mock sentence_transformers module in sys.modules for lazy import."""
    mock_module = MagicMock()
    mock_cls = MagicMock()
    mock_module.SentenceTransformer = mock_cls
    with patch.dict(sys.modules, {"sentence_transformers": mock_module}):
        yield mock_cls


class TestGetBgeM3Model:
    """Tests for get_bge_m3_model() singleton function."""

    def test_singleton_returns_same_instance(self, mock_flag_embedding):
        """Test that get_bge_m3_model returns the same instance on multiple calls."""
        from src.models.embedding_model import get_bge_m3_model

        mock_instance = MagicMock()
        mock_flag_embedding.return_value = mock_instance

        model1 = get_bge_m3_model()
        model2 = get_bge_m3_model()
        model3 = get_bge_m3_model()

        assert model1 is model2
        assert model2 is model3
        assert mock_flag_embedding.call_count == 1

    def test_default_initialization_parameters(self, mock_flag_embedding):
        """Test that default parameters are passed correctly to the model."""
        from src.models.embedding_model import get_bge_m3_model

        mock_flag_embedding.return_value = MagicMock()

        get_bge_m3_model()

        mock_flag_embedding.assert_called_once_with(
            "BAAI/bge-m3",
            use_fp16=True,
            device=None,
        )

    def test_custom_initialization_parameters(self, mock_flag_embedding):
        """Test that custom parameters are passed correctly to the model."""
        from src.models.embedding_model import get_bge_m3_model

        mock_flag_embedding.return_value = MagicMock()

        get_bge_m3_model(use_fp16=False, device="cuda")

        mock_flag_embedding.assert_called_once_with(
            "BAAI/bge-m3",
            use_fp16=False,
            device="cuda",
        )

    def test_subsequent_calls_ignore_parameters(self, mock_flag_embedding):
        """Test that parameters on subsequent calls are ignored (singleton already created)."""
        from src.models.embedding_model import get_bge_m3_model

        mock_instance = MagicMock()
        mock_flag_embedding.return_value = mock_instance

        model1 = get_bge_m3_model(use_fp16=True, device="cpu")
        model2 = get_bge_m3_model(use_fp16=False, device="cuda")

        assert model1 is model2
        mock_flag_embedding.assert_called_once_with(
            "BAAI/bge-m3",
            use_fp16=True,
            device="cpu",
        )

    def test_returns_bgem3flagmodel_instance(self, mock_flag_embedding):
        """Test that the returned object is the BGEM3FlagModel mock."""
        from src.models.embedding_model import get_bge_m3_model

        mock_instance = MagicMock()
        mock_instance.some_attribute = "test_value"
        mock_flag_embedding.return_value = mock_instance

        model = get_bge_m3_model()

        assert model is mock_instance
        assert model.some_attribute == "test_value"


class TestGetSentenceTransformer:
    """Tests for get_sentence_transformer() singleton function."""

    def test_singleton_returns_same_instance(self, mock_sentence_transformers):
        """Test that get_sentence_transformer returns the same instance on multiple calls."""
        from src.models.embedding_model import get_sentence_transformer

        mock_instance = MagicMock()
        mock_sentence_transformers.return_value = mock_instance

        st1 = get_sentence_transformer()
        st2 = get_sentence_transformer()
        st3 = get_sentence_transformer()

        assert st1 is st2
        assert st2 is st3
        assert mock_sentence_transformers.call_count == 1

    def test_default_model_name(self, mock_sentence_transformers):
        """Test that default model name is BAAI/bge-m3."""
        from src.models.embedding_model import get_sentence_transformer

        mock_sentence_transformers.return_value = MagicMock()

        get_sentence_transformer()

        mock_sentence_transformers.assert_called_once_with("BAAI/bge-m3")

    def test_custom_model_name(self, mock_sentence_transformers):
        """Test that custom model name is used on first call."""
        from src.models.embedding_model import get_sentence_transformer

        mock_sentence_transformers.return_value = MagicMock()

        get_sentence_transformer(model_name="sentence-transformers/all-MiniLM-L6-v2")

        mock_sentence_transformers.assert_called_once_with("sentence-transformers/all-MiniLM-L6-v2")

    def test_subsequent_calls_ignore_model_name(self, mock_sentence_transformers):
        """Test that model_name on subsequent calls is ignored."""
        from src.models.embedding_model import get_sentence_transformer

        mock_instance = MagicMock()
        mock_sentence_transformers.return_value = mock_instance

        st1 = get_sentence_transformer(model_name="model-a")
        st2 = get_sentence_transformer(model_name="model-b")

        assert st1 is st2
        mock_sentence_transformers.assert_called_once_with("model-a")


class TestClearModels:
    """Tests for clear_models() utility function."""

    def test_clear_models_resets_bge_m3(self, mock_flag_embedding, mock_sentence_transformers):
        """Test that clear_models() clears the BGE-M3 singleton."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import clear_models, get_bge_m3_model

        mock_flag_embedding.return_value = MagicMock()

        get_bge_m3_model()
        assert embedding_module._bge_m3_model is not None

        with patch("gc.collect", return_value=0):
            clear_models()
        assert embedding_module._bge_m3_model is None

    def test_clear_models_resets_sentence_transformer(
        self, mock_flag_embedding, mock_sentence_transformers
    ):
        """Test that clear_models() clears the SentenceTransformer singleton."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import clear_models, get_sentence_transformer

        mock_sentence_transformers.return_value = MagicMock()

        get_sentence_transformer()
        assert embedding_module._sentence_transformer is not None

        with patch("gc.collect", return_value=0):
            clear_models()
        assert embedding_module._sentence_transformer is None

    def test_clear_models_allows_new_initialization(
        self, mock_flag_embedding, mock_sentence_transformers
    ):
        """Test that after clear_models(), new instances can be created."""
        from src.models.embedding_model import clear_models, get_bge_m3_model

        mock_instance_1 = MagicMock(name="instance1")
        mock_instance_2 = MagicMock(name="instance2")
        mock_flag_embedding.side_effect = [mock_instance_1, mock_instance_2]

        model1 = get_bge_m3_model()
        assert model1 is mock_instance_1

        with patch("gc.collect", return_value=0):
            clear_models()

        model2 = get_bge_m3_model()
        assert model2 is mock_instance_2
        assert model1 is not model2
        assert mock_flag_embedding.call_count == 2

    def test_clear_models_calls_gc_collect(self, mock_flag_embedding, mock_sentence_transformers):
        """Test that clear_models() triggers garbage collection."""
        from src.models.embedding_model import clear_models, get_bge_m3_model

        mock_flag_embedding.return_value = MagicMock()

        get_bge_m3_model()

        with patch("gc.collect") as mock_gc:
            clear_models()
            mock_gc.assert_called_once()

    def test_clear_models_when_no_models_loaded(self):
        """Test that clear_models() works safely when no models are loaded."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import clear_models

        assert embedding_module._bge_m3_model is None
        assert embedding_module._sentence_transformer is None

        with patch("gc.collect", return_value=0):
            clear_models()

        assert embedding_module._bge_m3_model is None
        assert embedding_module._sentence_transformer is None


class TestSingletonIsolation:
    """Tests for isolation between the two singletons."""

    def test_singletons_are_independent(self, mock_flag_embedding, mock_sentence_transformers):
        """Test that BGE-M3 and SentenceTransformer singletons are separate."""
        from src.models.embedding_model import get_bge_m3_model, get_sentence_transformer

        mock_bge_instance = MagicMock(name="bge_model")
        mock_st_instance = MagicMock(name="st_model")
        mock_flag_embedding.return_value = mock_bge_instance
        mock_sentence_transformers.return_value = mock_st_instance

        bge_model = get_bge_m3_model()
        st_model = get_sentence_transformer()

        assert bge_model is not st_model
        assert bge_model is mock_bge_instance
        assert st_model is mock_st_instance

    def test_clear_affects_both_singletons(self, mock_flag_embedding, mock_sentence_transformers):
        """Test that clear_models() clears both singletons at once."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import (
            clear_models,
            get_bge_m3_model,
            get_sentence_transformer,
        )

        mock_flag_embedding.return_value = MagicMock()
        mock_sentence_transformers.return_value = MagicMock()

        get_bge_m3_model()
        get_sentence_transformer()

        assert embedding_module._bge_m3_model is not None
        assert embedding_module._sentence_transformer is not None

        with patch("gc.collect", return_value=0):
            clear_models()

        assert embedding_module._bge_m3_model is None
        assert embedding_module._sentence_transformer is None


class TestLogging:
    """Tests for logging behavior in the singleton functions."""

    def test_logs_info_on_first_initialization(self, mock_flag_embedding):
        """Test that info is logged on first model initialization."""
        from src.models.embedding_model import get_bge_m3_model

        mock_flag_embedding.return_value = MagicMock()

        with patch("src.models.embedding_model.logger") as mock_logger:
            get_bge_m3_model()

            assert mock_logger.info.call_count == 2
            first_call_args = mock_logger.info.call_args_list[0][0][0]
            assert "Loading BGE-M3 model" in first_call_args
            second_call_args = mock_logger.info.call_args_list[1][0][0]
            assert "loaded successfully" in second_call_args

    def test_logs_debug_on_subsequent_calls(self, mock_flag_embedding):
        """Test that debug is logged on subsequent calls (existing instance)."""
        from src.models.embedding_model import get_bge_m3_model

        mock_flag_embedding.return_value = MagicMock()

        get_bge_m3_model()

        with patch("src.models.embedding_model.logger") as mock_logger:
            get_bge_m3_model()
            mock_logger.debug.assert_called_once()
            assert "existing" in mock_logger.debug.call_args[0][0].lower()

    def test_logs_info_on_clear(self, mock_flag_embedding, mock_sentence_transformers):
        """Test that info is logged when clearing models."""
        from src.models.embedding_model import clear_models, get_bge_m3_model

        mock_flag_embedding.return_value = MagicMock()

        get_bge_m3_model()

        with (
            patch("src.models.embedding_model.logger") as mock_logger,
            patch("gc.collect", return_value=0),
        ):
            clear_models()
            mock_logger.info.assert_called()
            clear_call_args = mock_logger.info.call_args[0][0]
            assert "Clearing" in clear_call_args


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_model_initialization_error_propagates(self, mock_flag_embedding):
        """Test that exceptions during model initialization are propagated."""
        from src.models.embedding_model import get_bge_m3_model

        mock_flag_embedding.side_effect = RuntimeError("CUDA out of memory")

        with pytest.raises(RuntimeError, match="CUDA out of memory"):
            get_bge_m3_model()

    def test_singleton_state_after_failed_init(self, mock_flag_embedding):
        """Test that singleton remains None after failed initialization."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import get_bge_m3_model

        mock_flag_embedding.side_effect = RuntimeError("Model load failed")

        with pytest.raises(RuntimeError):
            get_bge_m3_model()

        assert embedding_module._bge_m3_model is None

    def test_retry_after_failed_initialization(self, mock_flag_embedding):
        """Test that initialization can be retried after a failure."""
        import src.models.embedding_model as embedding_module
        from src.models.embedding_model import get_bge_m3_model

        mock_instance = MagicMock()
        mock_flag_embedding.side_effect = [RuntimeError("First fail"), mock_instance]

        with pytest.raises(RuntimeError):
            get_bge_m3_model()

        assert embedding_module._bge_m3_model is None

        result = get_bge_m3_model()
        assert result is mock_instance
        assert embedding_module._bge_m3_model is mock_instance

    def test_device_parameter_none_is_auto(self, mock_flag_embedding):
        """Test that device=None means auto-detection."""
        from src.models.embedding_model import get_bge_m3_model

        mock_flag_embedding.return_value = MagicMock()

        get_bge_m3_model(device=None)

        call_kwargs = mock_flag_embedding.call_args[1]
        assert call_kwargs["device"] is None

    def test_use_fp16_false(self, mock_flag_embedding):
        """Test that use_fp16=False is passed correctly."""
        from src.models.embedding_model import get_bge_m3_model

        mock_flag_embedding.return_value = MagicMock()

        get_bge_m3_model(use_fp16=False)

        call_kwargs = mock_flag_embedding.call_args[1]
        assert call_kwargs["use_fp16"] is False

    def test_empty_model_name_passed_through(self, mock_sentence_transformers):
        """Test that empty string model name is passed (may fail in real code)."""
        from src.models.embedding_model import get_sentence_transformer

        mock_sentence_transformers.return_value = MagicMock()

        get_sentence_transformer(model_name="")

        mock_sentence_transformers.assert_called_once_with("")

    def test_import_error_when_flagembedding_missing(self):
        """Test that ImportError is raised with helpful message when FlagEmbedding is absent."""
        from src.models.embedding_model import get_bge_m3_model

        # Ensure FlagEmbedding is NOT in sys.modules
        with patch.dict(sys.modules, {"FlagEmbedding": None}):
            with pytest.raises(ImportError, match="ml-local"):
                get_bge_m3_model()

    def test_import_error_when_sentence_transformers_missing(self):
        """Test that ImportError is raised with helpful message when sentence_transformers absent."""
        from src.models.embedding_model import get_sentence_transformer

        with patch.dict(sys.modules, {"sentence_transformers": None}):
            with pytest.raises(ImportError, match="ml-local"):
                get_sentence_transformer()
