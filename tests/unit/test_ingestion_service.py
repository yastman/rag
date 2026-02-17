"""Unit tests for IngestionService.

Tests the high-level ingestion service without requiring
external services (Qdrant, Voyage AI, CocoIndex).

Milestone J: Document Ingestion Pipeline (2026-02-02)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.service import (
    IngestionService,
    IngestionStats,
    get_ingestion_status,
    ingest_from_directory,
    ingest_from_gdrive,
)


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client."""
    client = MagicMock()
    collection_info = MagicMock()
    collection_info.points_count = 100
    collection_info.vectors_count = 100
    collection_info.indexed_vectors_count = 100
    collection_info.status = "green"
    client.get_collection.return_value = collection_info
    return client


@pytest.fixture
def service(mock_qdrant_client):
    """Create IngestionService with mocked Qdrant."""
    svc = IngestionService(
        qdrant_url="http://localhost:6333",
        collection_name="test_collection",
    )
    svc._qdrant_client = mock_qdrant_client
    return svc


class TestIngestionService:
    """Tests for IngestionService class."""

    def test_init_defaults(self):
        """Test service initialization with defaults."""
        service = IngestionService()

        assert service.qdrant_url == "http://localhost:6333"
        assert service.collection_name == "documents"
        assert service.chunk_size == 512
        assert service.chunk_overlap == 50

    def test_init_custom_params(self):
        """Test service initialization with custom parameters."""
        service = IngestionService(
            qdrant_url="http://custom:6333",
            collection_name="custom_collection",
            chunk_size=1024,
            chunk_overlap=100,
        )

        assert service.qdrant_url == "http://custom:6333"
        assert service.collection_name == "custom_collection"
        assert service.chunk_size == 1024
        assert service.chunk_overlap == 100

    async def test_ingest_directory_not_found(self, service):
        """Test ingestion with non-existent directory."""
        stats = await service.ingest_directory(Path("/nonexistent/path"))

        assert stats.total_documents == 0
        assert len(stats.errors) == 1
        assert "not found" in stats.errors[0].lower()

    async def test_ingest_directory_empty(self, service, tmp_path):
        """Test ingestion with empty directory."""
        with patch("src.ingestion.service.check_cocoindex_available", return_value=True):
            stats = await service.ingest_directory(tmp_path)

        assert stats.total_documents == 0
        assert len(stats.errors) == 1
        assert "no supported documents" in stats.errors[0].lower()

    async def test_ingest_directory_cocoindex_not_available(self, service, tmp_path):
        """Test ingestion when CocoIndex is not installed."""
        # Create a test file
        test_file = tmp_path / "test.md"
        test_file.write_text("# Test")

        with patch("src.ingestion.service.check_cocoindex_available", return_value=False):
            stats = await service.ingest_directory(tmp_path)

        assert len(stats.errors) == 1
        assert "cocoindex not available" in stats.errors[0].lower()

    async def test_ingest_directory_counts_documents(self, service, tmp_path):
        """Test that ingestion counts supported documents correctly."""
        # Create test files
        (tmp_path / "doc1.pdf").write_bytes(b"PDF content")
        (tmp_path / "doc2.md").write_text("# Markdown")
        (tmp_path / "doc3.txt").write_text("Plain text")
        (tmp_path / "ignored.xyz").write_text("Ignored")

        with patch("src.ingestion.service.check_cocoindex_available", return_value=True):
            with patch("src.ingestion.service.setup_and_run_flow", return_value={"success": True}):
                stats = await service.ingest_directory(tmp_path)

        assert stats.total_documents == 3  # pdf, md, txt (not xyz)

    async def test_ingest_gdrive_no_credentials(self, service):
        """Test GDrive ingestion without credentials."""
        service.google_service_account_key = None

        stats = await service.ingest_gdrive("fake_folder_id")

        assert len(stats.errors) == 1
        assert "GOOGLE_SERVICE_ACCOUNT_KEY" in stats.errors[0]

    async def test_ingest_gdrive_file_not_found(self, service):
        """Test GDrive ingestion with missing credentials file."""
        service.google_service_account_key = "/nonexistent/credentials.json"

        stats = await service.ingest_gdrive("fake_folder_id")

        assert len(stats.errors) == 1
        assert "not found" in stats.errors[0].lower()

    async def test_get_collection_stats(self, service, mock_qdrant_client):
        """Test getting collection statistics."""
        stats = await service.get_collection_stats()

        assert stats["name"] == "test_collection"
        assert stats["points_count"] == 100
        assert stats["vectors_count"] == 100
        mock_qdrant_client.get_collection.assert_called_once_with("test_collection")

    async def test_get_collection_stats_not_found(self, service, mock_qdrant_client):
        """Test getting stats for non-existent collection."""
        from qdrant_client.http.exceptions import UnexpectedResponse

        mock_qdrant_client.get_collection.side_effect = UnexpectedResponse(
            status_code=404,
            reason_phrase="Not Found",
            content=b"Collection not found",
            headers={},
        )

        stats = await service.get_collection_stats()

        assert stats["name"] == "test_collection"
        assert "error" in stats
        assert stats["points_count"] == 0

    async def test_close(self, service, mock_qdrant_client):
        """Test service cleanup."""
        await service.close()

        assert service._qdrant_client is None
        mock_qdrant_client.close.assert_called_once()


class TestIngestionStats:
    """Tests for IngestionStats dataclass."""

    def test_default_values(self):
        """Test default values."""
        stats = IngestionStats()

        assert stats.total_documents == 0
        assert stats.total_nodes == 0
        assert stats.indexed_nodes == 0
        assert stats.skipped_nodes == 0
        assert stats.duration_seconds == 0.0
        assert stats.errors == []

    def test_custom_values(self):
        """Test setting custom values."""
        stats = IngestionStats(
            total_documents=10,
            total_nodes=50,
            indexed_nodes=45,
            skipped_nodes=5,
            duration_seconds=12.5,
            errors=["Error 1", "Error 2"],
        )

        assert stats.total_documents == 10
        assert stats.total_nodes == 50
        assert stats.indexed_nodes == 45
        assert stats.skipped_nodes == 5
        assert stats.duration_seconds == 12.5
        assert len(stats.errors) == 2


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    async def test_ingest_from_directory(self, tmp_path):
        """Test convenience function for directory ingestion."""
        with patch.object(IngestionService, "ingest_directory") as mock_ingest:
            with patch.object(IngestionService, "close") as mock_close:
                mock_ingest.return_value = IngestionStats(total_documents=5)

                stats = await ingest_from_directory(tmp_path)

                assert stats.total_documents == 5
                mock_close.assert_called_once()

    async def test_ingest_from_gdrive(self):
        """Test convenience function for GDrive ingestion."""
        with patch.object(IngestionService, "ingest_gdrive") as mock_ingest:
            with patch.object(IngestionService, "close") as mock_close:
                mock_ingest.return_value = IngestionStats(errors=["Test error"])

                stats = await ingest_from_gdrive("folder_id")

                assert len(stats.errors) == 1
                mock_close.assert_called_once()

    async def test_get_ingestion_status(self):
        """Test convenience function for getting status."""
        with patch.object(IngestionService, "get_collection_stats") as mock_stats:
            with patch.object(IngestionService, "close") as mock_close:
                mock_stats.return_value = {"name": "test", "points_count": 100}

                status = await get_ingestion_status()

                assert status["points_count"] == 100
                mock_close.assert_called_once()
