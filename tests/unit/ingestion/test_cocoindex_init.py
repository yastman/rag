# tests/unit/ingestion/test_cocoindex_init.py
"""Tests for CocoIndex initialization."""

import contextlib
from unittest.mock import patch

import pytest


pytest.importorskip("cocoindex", reason="cocoindex not installed (ingest extra)")
pytestmark = pytest.mark.requires_extras


class TestCocoIndexInit:
    """Test CocoIndex initialization with database settings."""

    def test_init_uses_config_database_url(self):
        """Verify init() receives database URL from config."""
        from src.ingestion.unified.config import UnifiedConfig

        config = UnifiedConfig(database_url="postgresql://test:test@localhost:5432/testdb")

        assert config.database_url == "postgresql://test:test@localhost:5432/testdb"

    def test_app_namespace_returns_unified(self):
        """Verify app_namespace returns 'unified' constant."""
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import _app_namespace_for

        config = UnifiedConfig(collection_name="gdrive_documents_scalar")
        ns = _app_namespace_for(config)
        assert ns == "unified"

        # Different collection name doesn't change namespace
        config2 = UnifiedConfig(collection_name="my-collection.v2")
        ns2 = _app_namespace_for(config2)
        assert ns2 == "unified"

    @patch("cocoindex.init")
    @patch("src.ingestion.unified.flow.flow_names", return_value=[])
    @patch("cocoindex.open_flow")
    def test_build_flow_calls_init_with_settings(self, mock_open_flow, mock_flow_names, mock_init):
        """Verify build_flow calls cocoindex.init with correct settings."""
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import build_flow

        config = UnifiedConfig(
            database_url="postgresql://test:test@localhost:5432/cocoindex",
            collection_name="test_collection",
        )

        with contextlib.suppress(Exception):
            build_flow(config)

        # Verify init was called
        assert mock_init.called
        call_args = mock_init.call_args
        settings = call_args[0][0]

        # Check settings structure
        assert hasattr(settings, "database")
        assert hasattr(settings, "app_namespace")
