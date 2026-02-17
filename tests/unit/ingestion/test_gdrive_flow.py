"""Tests for Google Drive local watcher flow.

DEPRECATED: src.ingestion.gdrive_flow is superseded by unified pipeline.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.legacy_api


class TestGDriveFlowConfig:
    """Test flow configuration."""

    def test_default_config_values(self):
        """Config should have sensible defaults."""
        from src.ingestion.gdrive_flow import GDriveFlowConfig

        # Clear GDRIVE_SYNC_DIR so we test the actual default (dotenv may set it)
        env = os.environ.copy()
        env.pop("GDRIVE_SYNC_DIR", None)
        with patch.dict("os.environ", env, clear=True):
            config = GDriveFlowConfig()

            # Default is ~/drive-sync expanded to user's home
            assert config.sync_dir == os.path.expanduser("~/drive-sync")
        assert config.collection_name == "gdrive_documents_bge"
        assert config.watch_interval_seconds == 60
        assert config.docling_url == "http://localhost:5001"

    def test_config_from_env(self):
        """Config should read from environment variables."""
        from src.ingestion.gdrive_flow import GDriveFlowConfig

        with patch.dict(
            "os.environ",
            {
                "GDRIVE_SYNC_DIR": "/custom/path",
                "QDRANT_URL": "http://custom:6333",
                "GDRIVE_COLLECTION_NAME": "custom_collection",
            },
        ):
            config = GDriveFlowConfig()

            assert config.sync_dir == "/custom/path"
            assert config.qdrant_url == "http://custom:6333"
            assert config.collection_name == "custom_collection"


class TestGDriveFileProcessor:
    """Test file processor logic."""

    def test_supported_extensions(self):
        """Processor should support expected file types."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor

        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)

        assert processor._is_supported_file(Path("doc.pdf"))
        assert processor._is_supported_file(Path("doc.docx"))
        assert processor._is_supported_file(Path("doc.xlsx"))
        assert processor._is_supported_file(Path("doc.pptx"))
        assert processor._is_supported_file(Path("doc.md"))
        assert processor._is_supported_file(Path("doc.txt"))
        assert not processor._is_supported_file(Path("image.jpg"))
        assert not processor._is_supported_file(Path(".hidden"))

    def test_hidden_files_not_supported(self):
        """Hidden files should not be supported."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor

        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)

        assert not processor._is_supported_file(Path(".DS_Store"))
        assert not processor._is_supported_file(Path(".gitignore"))

    def test_temp_files_not_supported(self):
        """Temp files (Word lock files) should not be supported."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor

        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)

        assert not processor._is_supported_file(Path("~$document.docx"))
        assert not processor._is_supported_file(Path("~$report.xlsx"))


class TestComputeFileId:
    """Test file ID computation."""

    def test_compute_file_id_deterministic(self):
        """File ID should be deterministic for same path."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor, GDriveFlowConfig

        config = GDriveFlowConfig(sync_dir="/data/drive-sync")
        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)
        processor.config = config
        processor.sync_dir = Path(config.sync_dir)

        id1 = processor._compute_file_id(Path("/data/drive-sync/folder/doc.pdf"))
        id2 = processor._compute_file_id(Path("/data/drive-sync/folder/doc.pdf"))

        assert id1 == id2

    def test_compute_file_id_different_for_different_paths(self):
        """Different paths should produce different IDs."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor, GDriveFlowConfig

        config = GDriveFlowConfig(sync_dir="/data/drive-sync")
        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)
        processor.config = config
        processor.sync_dir = Path(config.sync_dir)

        id1 = processor._compute_file_id(Path("/data/drive-sync/folder/doc1.pdf"))
        id2 = processor._compute_file_id(Path("/data/drive-sync/folder/doc2.pdf"))

        assert id1 != id2

    def test_compute_file_id_uses_relative_path(self):
        """File ID should be based on relative path only."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor, GDriveFlowConfig

        # Two different sync dirs, same relative path
        config1 = GDriveFlowConfig(sync_dir="/data/drive-sync")
        processor1 = GDriveFileProcessor.__new__(GDriveFileProcessor)
        processor1.config = config1
        processor1.sync_dir = Path(config1.sync_dir)

        config2 = GDriveFlowConfig(sync_dir="/other/drive-sync")
        processor2 = GDriveFileProcessor.__new__(GDriveFileProcessor)
        processor2.config = config2
        processor2.sync_dir = Path(config2.sync_dir)

        id1 = processor1._compute_file_id(Path("/data/drive-sync/folder/doc.pdf"))
        id2 = processor2._compute_file_id(Path("/other/drive-sync/folder/doc.pdf"))

        # Same relative path -> same ID
        assert id1 == id2


class TestComputeContentHash:
    """Test content hash computation."""

    def test_compute_content_hash_deterministic(self, tmp_path):
        """Content hash should be deterministic for same content."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor

        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)

        # Create test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        hash1 = processor._compute_content_hash(test_file)
        hash2 = processor._compute_content_hash(test_file)

        assert hash1 == hash2

    def test_compute_content_hash_different_for_different_content(self, tmp_path):
        """Different content should produce different hashes."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor

        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)

        file1 = tmp_path / "file1.txt"
        file1.write_text("content one")

        file2 = tmp_path / "file2.txt"
        file2.write_text("content two")

        hash1 = processor._compute_content_hash(file1)
        hash2 = processor._compute_content_hash(file2)

        assert hash1 != hash2


class TestNeedsProcessing:
    """Test change detection logic."""

    def test_needs_processing_new_file(self, tmp_path):
        """New files should need processing."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor, GDriveFlowConfig

        config = GDriveFlowConfig(sync_dir=str(tmp_path))
        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)
        processor.config = config
        processor.sync_dir = tmp_path
        processor._processed = {}

        test_file = tmp_path / "new.txt"
        test_file.write_text("new content")

        assert processor._needs_processing(test_file, "new_file_id")

    def test_needs_processing_unchanged_file(self, tmp_path):
        """Unchanged files should not need processing."""
        from datetime import UTC, datetime

        from src.ingestion.gdrive_flow import (
            GDriveFileProcessor,
            GDriveFlowConfig,
            ProcessedFile,
        )

        config = GDriveFlowConfig(sync_dir=str(tmp_path))
        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)
        processor.config = config
        processor.sync_dir = tmp_path

        test_file = tmp_path / "existing.txt"
        test_file.write_text("existing content")

        # Record as already processed with same hash
        content_hash = processor._compute_content_hash(test_file)
        processor._processed = {
            "existing_id": ProcessedFile(
                file_path="existing.txt",
                file_id="existing_id",
                content_hash=content_hash,
                chunks_count=5,
                processed_at=datetime.now(UTC),
            )
        }

        assert not processor._needs_processing(test_file, "existing_id")

    def test_needs_processing_changed_file(self, tmp_path):
        """Changed files should need processing."""
        from datetime import UTC, datetime

        from src.ingestion.gdrive_flow import (
            GDriveFileProcessor,
            GDriveFlowConfig,
            ProcessedFile,
        )

        config = GDriveFlowConfig(sync_dir=str(tmp_path))
        processor = GDriveFileProcessor.__new__(GDriveFileProcessor)
        processor.config = config
        processor.sync_dir = tmp_path

        test_file = tmp_path / "changed.txt"
        test_file.write_text("original content")

        # Record with old hash
        processor._processed = {
            "changed_id": ProcessedFile(
                file_path="changed.txt",
                file_id="changed_id",
                content_hash="old_hash_different",
                chunks_count=5,
                processed_at=datetime.now(UTC),
            )
        }

        # File content changed (different hash)
        assert processor._needs_processing(test_file, "changed_id")


class TestProcessedFile:
    """Test ProcessedFile dataclass."""

    def test_processed_file_creation(self):
        """ProcessedFile should store all fields."""
        from datetime import UTC, datetime

        from src.ingestion.gdrive_flow import ProcessedFile

        now = datetime.now(UTC)
        record = ProcessedFile(
            file_path="folder/doc.pdf",
            file_id="abc123",
            content_hash="def456",
            chunks_count=10,
            processed_at=now,
        )

        assert record.file_path == "folder/doc.pdf"
        assert record.file_id == "abc123"
        assert record.content_hash == "def456"
        assert record.chunks_count == 10
        assert record.processed_at == now
        assert record.error is None

    def test_processed_file_with_error(self):
        """ProcessedFile should store error when present."""
        from datetime import UTC, datetime

        from src.ingestion.gdrive_flow import ProcessedFile

        record = ProcessedFile(
            file_path="folder/doc.pdf",
            file_id="abc123",
            content_hash="",
            chunks_count=0,
            processed_at=datetime.now(UTC),
            error="Connection timeout",
        )

        assert record.error == "Connection timeout"


class TestGetMimeType:
    """Test MIME type detection."""

    def test_get_mime_type_pdf(self):
        """PDF should return correct MIME type."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor

        assert GDriveFileProcessor._get_mime_type(Path("doc.pdf")) == "application/pdf"

    def test_get_mime_type_docx(self):
        """DOCX should return correct MIME type."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor

        mime = GDriveFileProcessor._get_mime_type(Path("doc.docx"))
        assert "wordprocessingml" in mime

    def test_get_mime_type_markdown(self):
        """Markdown should return correct MIME type."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor

        assert GDriveFileProcessor._get_mime_type(Path("doc.md")) == "text/markdown"

    def test_get_mime_type_unknown(self):
        """Unknown extension should return octet-stream."""
        from src.ingestion.gdrive_flow import GDriveFileProcessor

        mime = GDriveFileProcessor._get_mime_type(Path("file.xyz"))
        assert mime == "application/octet-stream"
