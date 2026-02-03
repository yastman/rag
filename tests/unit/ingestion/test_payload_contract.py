# tests/unit/ingestion/test_payload_contract.py
"""Tests for payload contract compliance."""

from unittest.mock import MagicMock


class TestPayloadContract:
    """Test that payload meets bot requirements."""

    def test_payload_has_required_fields(self):
        """Payload must have page_content, metadata dict, and flat file_id."""
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

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
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

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
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

        id1 = QdrantHybridWriter.generate_point_id("file123", "page_1_offset_0")
        id2 = QdrantHybridWriter.generate_point_id("file123", "page_1_offset_0")
        id3 = QdrantHybridWriter.generate_point_id("file123", "page_1_offset_1")

        assert id1 == id2  # Same input = same output
        assert id1 != id3  # Different chunk_location = different ID

    def test_fallback_chunk_location(self):
        """Should fallback gracefully when no docling meta."""
        from src.ingestion.unified.qdrant_writer import QdrantHybridWriter

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
