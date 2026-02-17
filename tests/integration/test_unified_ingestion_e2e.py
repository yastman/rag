# tests/integration/test_unified_ingestion_e2e.py
"""E2E tests for unified ingestion pipeline."""

import hashlib
import os

import pytest


pytestmark = pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Set RUN_INTEGRATION_TESTS=1 to run integration tests",
)


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


class TestUnifiedPipelinePayload:
    """Tests for payload contract compliance."""

    async def test_payload_has_required_fields(
        self, temp_sync_dir, test_collection_name, qdrant_client, cleanup_collection
    ):
        """File goes through pipeline with correct payload format."""
        import cocoindex
        from qdrant_client.models import Distance, Modifier, SparseVectorParams, VectorParams

        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import build_flow

        # Configure for test
        os.environ["GDRIVE_SYNC_DIR"] = str(temp_sync_dir)
        os.environ["GDRIVE_COLLECTION_NAME"] = test_collection_name

        # Create test collection with correct vector config
        qdrant_client.recreate_collection(
            collection_name=test_collection_name,
            vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
            sparse_vectors_config={"bm42": SparseVectorParams(modifier=Modifier.IDF)},
        )

        # Run ingestion
        config = UnifiedConfig(
            sync_dir=temp_sync_dir,
            collection_name=test_collection_name,
        )
        _flow = build_flow(config)
        cocoindex.setup_all_flows()
        cocoindex.update_all_flows()

        # Verify in Qdrant
        test_file = temp_sync_dir / "test.md"
        file_id = hashlib.sha256(str(test_file.relative_to(temp_sync_dir)).encode()).hexdigest()[
            :16
        ]

        results, _ = qdrant_client.scroll(
            collection_name=test_collection_name,
            scroll_filter={"must": [{"key": "metadata.file_id", "match": {"value": file_id}}]},
            limit=10,
            with_payload=True,
        )

        assert len(results) > 0, "No points found in Qdrant"

        # Check payload contract
        payload = results[0].payload
        assert "page_content" in payload, "Missing page_content"
        assert "metadata" in payload, "Missing metadata"
        assert isinstance(payload["metadata"], dict), "metadata should be dict"

        # Required metadata fields (for small-to-big)
        assert payload["metadata"]["file_id"] == file_id
        assert payload["metadata"]["doc_id"] == file_id
        assert "order" in payload["metadata"]
        assert "source" in payload["metadata"]

        # Flat file_id for fast delete
        assert payload["file_id"] == file_id

        # Cleanup CocoIndex
        cocoindex.drop_all_flows()


class TestUnifiedPipelineDeleteSemantics:
    """Tests for delete semantics."""

    async def test_delete_removes_points(
        self, temp_sync_dir, test_collection_name, qdrant_client, cleanup_collection
    ):
        """Deleting file removes points from Qdrant."""
        import cocoindex
        from qdrant_client.models import Distance, Modifier, SparseVectorParams, VectorParams

        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import build_flow

        os.environ["GDRIVE_SYNC_DIR"] = str(temp_sync_dir)
        os.environ["GDRIVE_COLLECTION_NAME"] = test_collection_name

        qdrant_client.recreate_collection(
            collection_name=test_collection_name,
            vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
            sparse_vectors_config={"bm42": SparseVectorParams(modifier=Modifier.IDF)},
        )

        config = UnifiedConfig(
            sync_dir=temp_sync_dir,
            collection_name=test_collection_name,
        )

        # First pass - index file
        _flow = build_flow(config)
        cocoindex.setup_all_flows()
        cocoindex.update_all_flows()

        # Delete file
        test_file = temp_sync_dir / "test.md"
        file_id = hashlib.sha256(str(test_file.relative_to(temp_sync_dir)).encode()).hexdigest()[
            :16
        ]
        test_file.unlink()

        # Second pass - should detect deletion
        cocoindex.update_all_flows()

        # Verify points removed
        count = qdrant_client.count(
            collection_name=test_collection_name,
            count_filter={"must": [{"key": "metadata.file_id", "match": {"value": file_id}}]},
        )
        assert count.count == 0, "Points should be deleted"

        # Cleanup
        cocoindex.drop_all_flows()
