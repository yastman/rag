"""Integration tests for Google Drive ingestion pipeline.

Requires:
- Qdrant running at localhost:6333
- docling-serve running at localhost:5001
- VOYAGE_API_KEY environment variable
"""

import contextlib
import os
import socket
import tempfile
from pathlib import Path

import pytest


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2.0)
        try:
            s.connect((host, port))
            return True
        except (OSError, TimeoutError):
            return False


# Skip if services not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("VOYAGE_API_KEY"),
        reason="VOYAGE_API_KEY not set",
    ),
    pytest.mark.skipif(
        not _port_open("localhost", 5001),
        reason="docling-serve not running on localhost:5001",
    ),
]


@pytest.fixture
def temp_sync_dir():
    """Create temporary sync directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create test markdown file
        md_file = Path(tmpdir) / "test_document.md"
        md_file.write_text("""# Test Document

## Introduction

This is a test document for the Google Drive ingestion pipeline.
It contains multiple sections to verify chunking works correctly.

## Main Content

The ingestion pipeline should:
1. Parse this markdown file
2. Split it into chunks
3. Generate embeddings
4. Store in Qdrant

## Conclusion

If you can search for this content, the pipeline is working!
""")

        yield tmpdir


@pytest.fixture
async def setup_collection():
    """Setup test collection."""
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        Distance,
        Modifier,
        SparseVectorParams,
        VectorParams,
    )

    client = QdrantClient(url="http://localhost:6333", timeout=30)

    # Create with unique name for test
    test_collection = "gdrive_documents_test"

    # Cleanup before
    with contextlib.suppress(Exception):
        client.delete_collection(test_collection)

    client.create_collection(
        collection_name=test_collection,
        vectors_config={"dense": VectorParams(size=1024, distance=Distance.COSINE)},
        sparse_vectors_config={"bm42": SparseVectorParams(modifier=Modifier.IDF)},
    )

    yield test_collection

    # Cleanup after
    with contextlib.suppress(Exception):
        client.delete_collection(test_collection)


async def test_full_ingestion_pipeline(temp_sync_dir, setup_collection):
    """Test complete ingestion from file to searchable vectors."""
    from qdrant_client import QdrantClient

    from src.ingestion.gdrive_flow import GDriveFlowConfig, run_once

    # Configure for test
    config = GDriveFlowConfig(
        sync_dir=temp_sync_dir,
        collection_name=setup_collection,
    )

    # Run ingestion
    results = await run_once(config)

    # Verify results
    assert len(results) == 1
    assert results[0].chunks_count > 0
    assert results[0].error is None

    # Verify searchable in Qdrant
    client = QdrantClient(url="http://localhost:6333", timeout=30)
    info = client.get_collection(setup_collection)

    assert info.points_count == results[0].chunks_count


async def test_replace_semantics_on_update(temp_sync_dir, setup_collection):
    """Test that re-processing replaces existing chunks."""
    from qdrant_client import QdrantClient

    from src.ingestion.gdrive_flow import GDriveFileProcessor, GDriveFlowConfig

    config = GDriveFlowConfig(
        sync_dir=temp_sync_dir,
        collection_name=setup_collection,
    )

    processor = GDriveFileProcessor(config)

    # First run
    results1 = await processor.process_directory()
    assert len(results1) == 1
    first_count = results1[0].chunks_count

    client = QdrantClient(url="http://localhost:6333", timeout=30)
    info1 = client.get_collection(setup_collection)
    assert info1.points_count == first_count

    # Modify file
    md_file = Path(temp_sync_dir) / "test_document.md"
    md_file.write_text("# Updated\n\nNew content with more text that is different.")

    # Second run
    results2 = await processor.process_directory()
    assert len(results2) == 1

    # Verify no duplicates (same point count as new file)
    info2 = client.get_collection(setup_collection)

    # Should have replaced, not duplicated
    assert info2.points_count == results2[0].chunks_count


async def test_deletion_removes_points(temp_sync_dir, setup_collection):
    """Deleting a file from the sync dir should delete its points from Qdrant."""
    from qdrant_client import QdrantClient

    from src.ingestion.gdrive_flow import GDriveFileProcessor, GDriveFlowConfig

    config = GDriveFlowConfig(
        sync_dir=temp_sync_dir,
        collection_name=setup_collection,
    )
    processor = GDriveFileProcessor(config)

    # First run (indexes the file)
    results1 = await processor.process_directory()
    assert len(results1) == 1

    client = QdrantClient(url="http://localhost:6333", timeout=30)
    info1 = client.get_collection(setup_collection)
    assert info1.points_count > 0

    # Delete file + run one more cycle (should reconcile deletions)
    (Path(temp_sync_dir) / "test_document.md").unlink()
    await processor.process_directory()

    info2 = client.get_collection(setup_collection)
    assert info2.points_count == 0


async def test_skip_unchanged_files(temp_sync_dir, setup_collection):
    """Unchanged files should not be re-processed."""
    from src.ingestion.gdrive_flow import GDriveFileProcessor, GDriveFlowConfig

    config = GDriveFlowConfig(
        sync_dir=temp_sync_dir,
        collection_name=setup_collection,
    )
    processor = GDriveFileProcessor(config)

    # First run
    results1 = await processor.process_directory()
    assert len(results1) == 1
    first_hash = results1[0].content_hash

    # Second run (same file, unchanged)
    results2 = await processor.process_directory()
    assert len(results2) == 1

    # Hash should be the same (file wasn't re-processed because unchanged)
    assert results2[0].content_hash == first_hash


async def test_multiple_files(temp_sync_dir, setup_collection):
    """Test processing multiple files."""
    from qdrant_client import QdrantClient

    from src.ingestion.gdrive_flow import GDriveFlowConfig, run_once

    # Create second file
    txt_file = Path(temp_sync_dir) / "second_file.txt"
    txt_file.write_text("This is a plain text file for testing multiple file ingestion.")

    config = GDriveFlowConfig(
        sync_dir=temp_sync_dir,
        collection_name=setup_collection,
    )

    results = await run_once(config)

    # Should process both files
    assert len(results) == 2
    total_chunks = sum(r.chunks_count for r in results)

    # Verify in Qdrant
    client = QdrantClient(url="http://localhost:6333", timeout=30)
    info = client.get_collection(setup_collection)
    assert info.points_count == total_chunks


async def test_unsupported_files_ignored(temp_sync_dir, setup_collection):
    """Unsupported file types should be ignored."""
    from src.ingestion.gdrive_flow import GDriveFlowConfig, run_once

    # Create unsupported file
    jpg_file = Path(temp_sync_dir) / "image.jpg"
    jpg_file.write_bytes(b"\xff\xd8\xff\xe0")  # JPEG magic bytes

    config = GDriveFlowConfig(
        sync_dir=temp_sync_dir,
        collection_name=setup_collection,
    )

    results = await run_once(config)

    # Only markdown file should be processed
    assert len(results) == 1
    assert results[0].file_path == "test_document.md"
