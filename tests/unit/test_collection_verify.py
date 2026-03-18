# tests/unit/test_collection_verify.py
"""Tests for collection verification mode."""

from unittest.mock import MagicMock


class TestCollectionVerify:
    """Test --verify-only mode."""

    def test_verify_returns_missing_indexes(self):
        """verify_collection should return list of missing indexes."""
        from scripts.setup_scalar_collection import verify_collection_indexes

        # Mock client with partial indexes
        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.payload_schema = {
            "file_id": MagicMock(data_type="keyword"),
            # Missing: metadata.file_id, metadata.doc_id, metadata.order, etc.
        }
        mock_client.get_collection.return_value = mock_info

        missing = verify_collection_indexes(mock_client, "test_collection")

        assert "metadata.file_id" in missing
        assert "metadata.doc_id" in missing
        assert "metadata.order" in missing
        assert "metadata.jurisdiction" in missing
        assert "metadata.audience" in missing
        assert "metadata.language" in missing

    def test_verify_returns_empty_when_complete(self):
        """verify_collection should return empty list when all indexes present."""
        from scripts.setup_scalar_collection import verify_collection_indexes

        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.payload_schema = {
            "file_id": MagicMock(data_type="keyword"),
            "metadata.file_id": MagicMock(data_type="keyword"),
            "metadata.doc_id": MagicMock(data_type="keyword"),
            "metadata.source": MagicMock(data_type="keyword"),
            "metadata.topic": MagicMock(data_type="keyword"),
            "metadata.doc_type": MagicMock(data_type="keyword"),
            "metadata.jurisdiction": MagicMock(data_type="keyword"),
            "metadata.audience": MagicMock(data_type="keyword"),
            "metadata.language": MagicMock(data_type="keyword"),
            "metadata.order": MagicMock(data_type="integer"),
            "metadata.chunk_order": MagicMock(data_type="integer"),
        }
        mock_client.get_collection.return_value = mock_info

        missing = verify_collection_indexes(mock_client, "test_collection")

        assert missing == []

    def test_verify_detects_wrong_type(self):
        """verify_collection should detect wrong index types."""
        from scripts.setup_scalar_collection import verify_collection_indexes

        mock_client = MagicMock()
        mock_info = MagicMock()
        mock_info.payload_schema = {
            "file_id": MagicMock(data_type="keyword"),
            "metadata.file_id": MagicMock(data_type="keyword"),
            "metadata.doc_id": MagicMock(data_type="keyword"),
            "metadata.source": MagicMock(data_type="keyword"),
            "metadata.topic": MagicMock(data_type="keyword"),
            "metadata.doc_type": MagicMock(data_type="keyword"),
            "metadata.order": MagicMock(data_type="keyword"),  # Wrong! Should be integer
            "metadata.chunk_order": MagicMock(data_type="integer"),
        }
        mock_client.get_collection.return_value = mock_info

        missing = verify_collection_indexes(mock_client, "test_collection")

        # Should report wrong type
        assert any("metadata.order" in m and "wrong type" in m for m in missing)
