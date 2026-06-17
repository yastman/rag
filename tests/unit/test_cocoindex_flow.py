"""Unit tests for CocoIndex flow definitions.

Tests the CocoIndex flow configuration and helper classes
without requiring the actual CocoIndex library.

Milestone J: Document Ingestion Pipeline (2026-02-02)
Note: Voyage AI embedding removed in #2631; BGE-M3 is the canonical path.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import src.ingestion.cocoindex_flow as cocoindex_flow
from src.ingestion.cocoindex_flow import (
    FlowConfig,
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
        assert config.vector_size == 1024
        assert config.refresh_interval_seconds == 60

    def test_custom_values(self):
        """Test custom configuration values."""
        config = FlowConfig(
            qdrant_url="http://custom:6333",
            collection_name="custom_docs",
            chunk_size=1024,
            chunk_overlap=100,
        )

        assert config.qdrant_url == "http://custom:6333"
        assert config.collection_name == "custom_docs"
        assert config.chunk_size == 1024
        assert config.chunk_overlap == 100

    def test_no_voyage_fields(self):
        """FlowConfig must not have voyage_api_key or voyage_model (#2631)."""
        config = FlowConfig()
        assert not hasattr(config, "voyage_api_key"), "voyage_api_key removed in #2631"
        assert not hasattr(config, "voyage_model"), "voyage_model removed in #2631"


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

    def test_successful_flow_execution_inside_running_event_loop(self):
        """Blocking mode should still work when the caller already has an event loop."""

        async def _run_inside_loop():
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
            mock_cocoindex.update_all_flows_async.assert_awaited_once()

        asyncio.run(_run_inside_loop())

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
            check_cocoindex_available,
            create_document_flow,
            setup_and_run_flow,
        )

        assert FlowConfig is not None
        assert callable(check_cocoindex_available)
        assert callable(create_document_flow)
        assert callable(setup_and_run_flow)

    def test_voyage_embed_function_not_exported(self):
        """VoyageEmbedFunction must not exist in cocoindex_flow (#2631)."""
        import src.ingestion.cocoindex_flow as flow_module

        assert not hasattr(flow_module, "VoyageEmbedFunction"), (
            "VoyageEmbedFunction removed in #2631"
        )

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
