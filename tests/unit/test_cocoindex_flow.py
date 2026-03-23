"""Unit tests for CocoIndex flow definitions.

Tests the CocoIndex flow configuration and helper classes
without requiring the actual CocoIndex library.

Milestone J: Document Ingestion Pipeline (2026-02-02)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np

import src.ingestion.cocoindex_flow as cocoindex_flow
from src.ingestion.cocoindex_flow import (
    FlowConfig,
    VoyageEmbedFunction,
    check_cocoindex_available,
    create_document_flow,
    setup_and_run_flow,
)


class TestFlowConfig:
    """Tests for FlowConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = FlowConfig()

        assert config.qdrant_url == "http://localhost:6333"
        assert config.collection_name == "documents"
        assert config.chunk_size == 512
        assert config.chunk_overlap == 50
        assert config.voyage_model == "voyage-4-large"
        assert config.vector_size == 1024
        assert config.refresh_interval_seconds == 60

    def test_custom_values(self):
        """Test custom configuration values."""
        config = FlowConfig(
            qdrant_url="http://custom:6333",
            collection_name="custom_docs",
            chunk_size=1024,
            chunk_overlap=100,
            voyage_model="voyage-3-large",
        )

        assert config.qdrant_url == "http://custom:6333"
        assert config.collection_name == "custom_docs"
        assert config.chunk_size == 1024
        assert config.chunk_overlap == 100
        assert config.voyage_model == "voyage-3-large"

    def test_env_var_defaults(self, monkeypatch):
        """Test that config reads from environment variables."""
        monkeypatch.setenv("QDRANT_URL", "http://env-qdrant:6333")
        monkeypatch.setenv("VOYAGE_API_KEY", "test-voyage-key")

        config = FlowConfig()

        assert config.qdrant_url == "http://env-qdrant:6333"
        assert config.voyage_api_key == "test-voyage-key"


class TestVoyageEmbedFunction:
    """Tests for VoyageEmbedFunction class."""

    def test_init_defaults(self):
        """Test initialization with defaults."""
        func = VoyageEmbedFunction()

        assert func.model == "voyage-4-large"
        assert func._service is None  # Lazy loaded

    def test_init_custom_model(self):
        """Test initialization with custom model."""
        func = VoyageEmbedFunction(
            api_key="test-key",
            model="voyage-3-large",
        )

        assert func.api_key == "test-key"
        assert func.model == "voyage-3-large"

    def test_call_embeds_texts(self):
        """Test that calling the function embeds texts."""
        func = VoyageEmbedFunction(api_key="test-key")

        # Mock the VoyageService
        mock_service = MagicMock()
        mock_service.embed_documents = AsyncMock(return_value=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        func._service = mock_service

        def _run_until_complete(coro):
            # Test double for loop.run_until_complete that avoids leaked coroutine warnings.
            coro.close()
            return [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

        with patch("asyncio.get_event_loop") as mock_loop:
            mock_loop.return_value.is_running.return_value = False
            mock_loop.return_value.run_until_complete.side_effect = _run_until_complete

            result = func(["text1", "text2"])

        assert len(result) == 2
        assert isinstance(result[0], np.ndarray)
        assert result[0].dtype == np.float32


class TestCheckCocoindexAvailable:
    """Tests for check_cocoindex_available function."""

    def test_returns_boolean(self):
        """Test that function returns a boolean."""
        result = check_cocoindex_available()
        assert isinstance(result, bool)


class TestCreateDocumentFlow:
    """Tests for create_document_flow function."""

    def test_returns_none_when_cocoindex_unavailable(self):
        """Test that None is returned when CocoIndex not available."""
        with patch.object(cocoindex_flow, "COCOINDEX_AVAILABLE", False):
            result = create_document_flow()

        assert result is None

    def test_creates_flow_when_available(self):
        """Test flow creation when CocoIndex is available."""
        with patch.object(cocoindex_flow, "COCOINDEX_AVAILABLE", True):
            # Mock cocoindex module with proper decorator signature
            mock_cocoindex = MagicMock()
            mock_cocoindex.flow_def = MagicMock(return_value=lambda f: f)

            with patch.object(cocoindex_flow, "cocoindex", mock_cocoindex):
                result = create_document_flow(
                    config=FlowConfig(collection_name="test"),
                    source_path="/test/path",
                )

        # Should return the flow function (not None)
        assert result is not None


class TestSetupAndRunFlow:
    """Tests for setup_and_run_flow function."""

    def test_returns_error_when_cocoindex_unavailable(self):
        """Test error return when CocoIndex not available."""
        with patch.object(cocoindex_flow, "COCOINDEX_AVAILABLE", False):
            result = setup_and_run_flow("/test/path")

        assert result["success"] is False
        assert "not available" in result["error"].lower()

    def test_handles_flow_creation_failure(self):
        """Test handling of flow creation failure."""
        with patch.object(cocoindex_flow, "COCOINDEX_AVAILABLE", True):
            with patch.object(cocoindex_flow, "create_document_flow", return_value=None):
                mock_cocoindex = MagicMock()
                with patch.object(cocoindex_flow, "cocoindex", mock_cocoindex):
                    result = setup_and_run_flow("/test/path")

        assert result["success"] is False
        assert "failed to create flow" in result["error"].lower()

    def test_successful_flow_execution(self):
        """Test successful flow execution."""
        with patch.object(cocoindex_flow, "COCOINDEX_AVAILABLE", True):
            mock_flow = MagicMock()
            with patch.object(cocoindex_flow, "create_document_flow", return_value=mock_flow):
                mock_cocoindex = MagicMock()
                mock_cocoindex.update_all_flows_async = AsyncMock(return_value={})
                with patch.object(cocoindex_flow, "cocoindex", mock_cocoindex):
                    config = FlowConfig(collection_name="test_collection")
                    result = setup_and_run_flow("/test/path", config=config)

        assert result["success"] is True
        assert result["flow_name"] == "DocumentIngestion"
        assert result["source_path"] == "/test/path"
        assert result["collection"] == "test_collection"

    def test_handles_exception(self):
        """Test handling of exceptions during flow execution."""
        with patch.object(cocoindex_flow, "COCOINDEX_AVAILABLE", True):
            mock_cocoindex = MagicMock()
            mock_cocoindex.init.side_effect = RuntimeError("Init failed")
            with patch.object(cocoindex_flow, "cocoindex", mock_cocoindex):
                result = setup_and_run_flow("/test/path")

        assert result["success"] is False
        assert "Init failed" in result["error"]


class TestModuleImports:
    """Tests for module-level imports and exports."""

    def test_exports_available(self):
        """Test that expected exports are available."""
        from src.ingestion.cocoindex_flow import (
            FlowConfig,
            VoyageEmbedFunction,
            check_cocoindex_available,
            create_document_flow,
            setup_and_run_flow,
        )

        assert FlowConfig is not None
        assert VoyageEmbedFunction is not None
        assert callable(check_cocoindex_available)
        assert callable(create_document_flow)
        assert callable(setup_and_run_flow)

    def test_ingestion_module_exports(self):
        """Test that ingestion module exports CocoIndex components."""
        from src.ingestion import (
            FlowConfig,
            IngestionService,
            IngestionStats,
            check_cocoindex_available,
            create_document_flow,
        )

        assert FlowConfig is not None
        assert callable(check_cocoindex_available)
        assert callable(create_document_flow)
        assert IngestionService is not None
        assert IngestionStats is not None
