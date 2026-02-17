# tests/unit/ingestion/test_target_sync_execution.py
"""Tests for sync execution in target connector."""

import asyncio

import pytest


pytest.importorskip("cocoindex", reason="cocoindex not installed (ingest extra)")
pytestmark = pytest.mark.requires_extras


@pytest.mark.xdist_group("cocoindex")
class TestTargetSyncExecution:
    """Test that mutate() works without asyncio.run() conflicts."""

    @pytest.fixture(autouse=True)
    def _skip_if_registry_collision(self):
        """Skip gracefully if cocoindex target_connector is already registered."""
        try:
            from src.ingestion.unified.targets.qdrant_hybrid_target import (  # noqa: F401
                QdrantHybridTargetConnector,
            )
        except ImportError as exc:
            pytest.skip(f"cocoindex not installed: {exc}")
        except RuntimeError as exc:
            if "already exists" in str(exc):
                pytest.skip(f"cocoindex registry collision under xdist: {exc}")
            raise

    def test_mutate_does_not_call_asyncio_run(self):
        """mutate() should not use asyncio.run() directly."""
        import inspect

        from src.ingestion.unified.targets.qdrant_hybrid_target import (
            QdrantHybridTargetConnector,
        )

        source = inspect.getsource(QdrantHybridTargetConnector.mutate)
        assert "asyncio.run(" not in source, "mutate() should not use asyncio.run()"

    def test_handle_methods_are_sync(self):
        """_handle_delete_with_state and _handle_upsert_with_state should be sync methods."""
        from src.ingestion.unified.targets.qdrant_hybrid_target import (
            QdrantHybridTargetConnector,
        )

        # After refactor, these should not be async
        assert not asyncio.iscoroutinefunction(
            QdrantHybridTargetConnector._handle_delete_with_state
        ), "_handle_delete_with_state should be sync"
        assert not asyncio.iscoroutinefunction(
            QdrantHybridTargetConnector._handle_upsert_with_state
        ), "_handle_upsert_with_state should be sync"

    def test_writer_has_sync_methods(self):
        """QdrantHybridWriter should have sync methods."""
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

        # Check method exists (will be added)
        assert hasattr(QdrantHybridWriter, "delete_file_sync")
        assert hasattr(QdrantHybridWriter, "upsert_chunks_sync")
