# tests/integration/test_unified_ingestion_e2e.py
"""E2E tests for unified ingestion pipeline."""

import os

import pytest


pytestmark = [
    pytest.mark.requires_services,
    pytest.mark.skipif(
        not os.getenv("RUN_INTEGRATION_TESTS"),
        reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests",
    ),
]


@pytest.fixture
def temp_sync_dir(tmp_path):
    """Create temporary sync directory with test files."""
    sync_dir = tmp_path / "sync"
    sync_dir.mkdir()

    # Create test markdown file
    test_file = sync_dir / "test.md"
    test_file.write_text("# Test Document\n\nThis is test content for ingestion.")

    return sync_dir


@pytest.fixture
def test_collection_name():
    """Unique collection name for test isolation."""
    return "test_unified_e2e"


@pytest.fixture
def qdrant_client():
    """Get Qdrant client."""
    from qdrant_client import QdrantClient

    return QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))


@pytest.fixture
def cleanup_collection(qdrant_client, test_collection_name):
    """Clean up test collection after test."""
    import contextlib

    yield
    with contextlib.suppress(Exception):
        qdrant_client.delete_collection(test_collection_name)
