# tests/unit/ingestion/test_payload_contract.py
"""Tests for payload contract compliance."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from src.ingestion.unified.qdrant_writer import QdrantHybridWriter


class TestPayloadContract:
    """Test that payload meets bot requirements."""

    def test_payload_has_required_fields(self):
        """Payload must have page_content, metadata dict, and flat file_id."""
        writer = QdrantHybridWriter.__new__(QdrantHybridWriter)

        chunk = MagicMock()
        chunk.text = "Test content"
        chunk.chunk_id = 0
        chunk.order = 0
        chunk.document_name = "test.pdf"
        chunk.section = "Introduction"
        chunk.page_range = (1, 2)
        chunk.extra_metadata = {"headings": ["Title"], "chunk_order": 0}

        file_metadata = {
            "file_name": "test.pdf",
            "mime_type": "application/pdf",
            "modified_time": "2026-02-03T12:00:00Z",
            "content_hash": "abc123",
        }

        payload = writer.build_payload(
            chunk=chunk,
            file_id="file123",
            source_path="docs/test.pdf",
            chunk_location="page_1_offset_0",
            file_metadata=file_metadata,
        )

        # Required top-level fields
        assert "page_content" in payload
        assert payload["page_content"] == "Test content"
        assert "metadata" in payload
        assert isinstance(payload["metadata"], dict)
        assert "file_id" in payload  # Flat for delete

        # Required metadata fields (for small-to-big)
        assert payload["metadata"]["file_id"] == "file123"
        assert payload["metadata"]["doc_id"] == "file123"
        assert payload["metadata"]["order"] == 0
        assert payload["metadata"]["chunk_order"] == 0
        assert payload["metadata"]["source"] == "docs/test.pdf"

    def test_chunk_location_stability(self):
        """chunk_location should be stable for same input."""
        chunk1 = MagicMock()
        chunk1.extra_metadata = {"docling_meta": {"page": 1, "offset": 100}}

        chunk2 = MagicMock()
        chunk2.extra_metadata = {"docling_meta": {"page": 1, "offset": 100}}

        loc1 = QdrantHybridWriter.get_chunk_location(chunk1, 0)
        loc2 = QdrantHybridWriter.get_chunk_location(chunk2, 0)

        assert loc1 == loc2
        assert loc1 == "page_1_offset_100"

    def test_point_id_deterministic(self):
        """point_id should be deterministic for same file_id + chunk_location."""
        id1 = QdrantHybridWriter.generate_point_id("file123", "page_1_offset_0")
        id2 = QdrantHybridWriter.generate_point_id("file123", "page_1_offset_0")
        id3 = QdrantHybridWriter.generate_point_id("file123", "page_1_offset_1")

        assert id1 == id2  # Same input = same output
        assert id1 != id3  # Different chunk_location = different ID

    def test_fallback_chunk_location(self):
        """Should fallback gracefully when no docling meta."""
        # No metadata
        chunk = MagicMock()
        chunk.extra_metadata = None
        chunk.order = None

        loc = QdrantHybridWriter.get_chunk_location(chunk, 5)
        assert loc == "chunk_5"

        # With order
        chunk.order = 3
        loc = QdrantHybridWriter.get_chunk_location(chunk, 5)
        assert loc == "order_3"


def _make_writer_with_mocks(mock_bge_client: MagicMock) -> QdrantHybridWriter:
    """Create QdrantHybridWriter bypassing __init__ and inject mock BGE client."""
    writer = QdrantHybridWriter.__new__(QdrantHybridWriter)
    writer.use_local_embeddings = True
    writer._bge_client = mock_bge_client
    writer._dense_semaphore = threading.Semaphore(1)
    writer.voyage = None
    return writer


class TestColbertVectorInUpsert:
    """Writer includes colbert multivectors in upserted points."""

    def test_embed_colbert_returns_nested_list(self):
        """_embed_colbert returns list[list[list[float]]] from bge_client."""
        mock_bge = MagicMock()
        colbert_result = MagicMock()
        colbert_result.colbert_vecs = [[[0.1] * 1024, [0.2] * 1024]]
        mock_bge.encode_colbert.return_value = colbert_result

        writer = _make_writer_with_mocks(mock_bge)

        result = writer._embed_colbert(["hello"])

        mock_bge.encode_colbert.assert_called_once_with(["hello"])
        assert result == [[[0.1] * 1024, [0.2] * 1024]]

    def test_embed_colbert_empty_returns_empty(self):
        """_embed_colbert with empty input returns [] without calling bge_client."""
        mock_bge = MagicMock()
        writer = _make_writer_with_mocks(mock_bge)

        result = writer._embed_colbert([])

        mock_bge.encode_colbert.assert_not_called()
        assert result == []

    def test_upsert_chunks_sync_point_has_colbert_vector(self):
        """upsert_chunks_sync points include 'colbert' key when use_local_embeddings=True."""
        from qdrant_client.models import PointStruct

        mock_bge = MagicMock()

        # Dense: 1 doc, 1024-dim
        dense_result = MagicMock()
        dense_result.vectors = [[0.1] * 1024]
        mock_bge.encode_dense.return_value = dense_result

        # Sparse: 1 doc
        sparse_result = MagicMock()
        sparse_result.weights = [{"indices": [1, 2], "values": [0.5, 0.3]}]
        mock_bge.encode_sparse.return_value = sparse_result

        # ColBERT: 1 doc, 2 tokens
        colbert_result = MagicMock()
        colbert_result.colbert_vecs = [[[0.1] * 1024, [0.2] * 1024]]
        mock_bge.encode_colbert.return_value = colbert_result

        writer = _make_writer_with_mocks(mock_bge)

        # Mock qdrant client
        mock_qdrant = MagicMock()
        mock_qdrant.count.return_value = MagicMock(count=0)
        writer.client = mock_qdrant

        # Create chunk
        chunk = MagicMock()
        chunk.text = "test chunk"
        chunk.order = 0
        chunk.chunk_id = 0
        chunk.document_name = "test.pdf"
        chunk.section = None
        chunk.page_range = None
        chunk.extra_metadata = {}

        writer.upsert_chunks_sync(
            chunks=[chunk],
            file_id="file123",
            source_path="docs/test.pdf",
            file_metadata={"file_name": "test.pdf"},
            collection_name="gdrive_documents_bge",
        )

        # Verify upsert was called and point has colbert vector
        mock_qdrant.upsert.assert_called_once()
        call_kwargs = mock_qdrant.upsert.call_args[1]
        points: list[PointStruct] = call_kwargs["points"]
        assert len(points) == 1

        point = points[0]
        assert isinstance(point.vector, dict)
        assert "dense" in point.vector
        assert "bm42" in point.vector
        assert "colbert" in point.vector
        assert point.vector["colbert"] == [[0.1] * 1024, [0.2] * 1024]
