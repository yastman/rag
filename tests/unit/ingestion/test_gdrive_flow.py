"""Unit tests for src/ingestion/gdrive_flow.py."""

from __future__ import annotations

import warnings
from pathlib import Path
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")

with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    from src.ingestion.gdrive_flow import GDriveFileProcessor, GDriveFlowConfig, ProcessedFile


# ---------------------------------------------------------------------------
# GDriveFlowConfig
# ---------------------------------------------------------------------------


class TestGDriveFlowConfig:
    def test_default_collection_name(self) -> None:
        config = GDriveFlowConfig()
        assert config.collection_name == "gdrive_documents_bge"

    def test_custom_sync_dir(self) -> None:
        config = GDriveFlowConfig(sync_dir="/tmp/test-sync")
        assert config.sync_dir == "/tmp/test-sync"

    def test_default_chunk_max_tokens(self) -> None:
        config = GDriveFlowConfig()
        assert config.chunk_max_tokens == 512

    def test_default_watch_interval(self) -> None:
        config = GDriveFlowConfig()
        assert config.watch_interval_seconds == 60

    def test_custom_qdrant_url(self) -> None:
        config = GDriveFlowConfig(qdrant_url="http://custom:6333")
        assert config.qdrant_url == "http://custom:6333"


# ---------------------------------------------------------------------------
# GDriveFileProcessor._is_supported_file
# ---------------------------------------------------------------------------


class TestIsSupportedFile:
    @pytest.fixture
    def processor(self, tmp_path: Path) -> GDriveFileProcessor:
        with (
            patch("src.ingestion.gdrive_flow.DoclingClient"),
            patch("src.ingestion.gdrive_flow.GDriveIndexer"),
        ):
            return GDriveFileProcessor(GDriveFlowConfig(sync_dir=str(tmp_path)))

    def test_pdf_supported(self, processor: GDriveFileProcessor, tmp_path: Path) -> None:
        assert processor._is_supported_file(tmp_path / "doc.pdf") is True

    def test_docx_supported(self, processor: GDriveFileProcessor, tmp_path: Path) -> None:
        assert processor._is_supported_file(tmp_path / "doc.docx") is True

    def test_txt_supported(self, processor: GDriveFileProcessor, tmp_path: Path) -> None:
        assert processor._is_supported_file(tmp_path / "readme.txt") is True

    def test_md_supported(self, processor: GDriveFileProcessor, tmp_path: Path) -> None:
        assert processor._is_supported_file(tmp_path / "notes.md") is True

    def test_html_supported(self, processor: GDriveFileProcessor, tmp_path: Path) -> None:
        assert processor._is_supported_file(tmp_path / "page.html") is True

    def test_py_not_supported(self, processor: GDriveFileProcessor, tmp_path: Path) -> None:
        assert processor._is_supported_file(tmp_path / "script.py") is False

    def test_hidden_file_not_supported(
        self, processor: GDriveFileProcessor, tmp_path: Path
    ) -> None:
        assert processor._is_supported_file(tmp_path / ".hidden.pdf") is False

    def test_temp_office_file_not_supported(
        self, processor: GDriveFileProcessor, tmp_path: Path
    ) -> None:
        assert processor._is_supported_file(tmp_path / "~$doc.docx") is False

    def test_uppercase_extension_supported(
        self, processor: GDriveFileProcessor, tmp_path: Path
    ) -> None:
        assert processor._is_supported_file(tmp_path / "DOC.PDF") is True


# ---------------------------------------------------------------------------
# GDriveFileProcessor._compute_file_id
# ---------------------------------------------------------------------------


class TestComputeFileId:
    @pytest.fixture
    def processor(self, tmp_path: Path) -> GDriveFileProcessor:
        with (
            patch("src.ingestion.gdrive_flow.DoclingClient"),
            patch("src.ingestion.gdrive_flow.GDriveIndexer"),
        ):
            return GDriveFileProcessor(GDriveFlowConfig(sync_dir=str(tmp_path)))

    def test_returns_16_char_hex(self, processor: GDriveFileProcessor, tmp_path: Path) -> None:
        file_id = processor._compute_file_id(tmp_path / "test.pdf")
        assert len(file_id) == 16
        assert all(c in "0123456789abcdef" for c in file_id)

    def test_deterministic(self, processor: GDriveFileProcessor, tmp_path: Path) -> None:
        path = tmp_path / "test.pdf"
        assert processor._compute_file_id(path) == processor._compute_file_id(path)

    def test_different_paths_different_ids(
        self, processor: GDriveFileProcessor, tmp_path: Path
    ) -> None:
        id1 = processor._compute_file_id(tmp_path / "a.pdf")
        id2 = processor._compute_file_id(tmp_path / "b.pdf")
        assert id1 != id2

    def test_nested_path(self, processor: GDriveFileProcessor, tmp_path: Path) -> None:
        path = tmp_path / "subdir" / "deep" / "file.pdf"
        file_id = processor._compute_file_id(path)
        assert len(file_id) == 16


# ---------------------------------------------------------------------------
# GDriveFileProcessor._get_mime_type
# ---------------------------------------------------------------------------


class TestGetMimeType:
    def test_pdf(self) -> None:
        assert GDriveFileProcessor._get_mime_type(Path("doc.pdf")) == "application/pdf"

    def test_docx(self) -> None:
        result = GDriveFileProcessor._get_mime_type(Path("doc.docx"))
        assert "wordprocessingml" in result

    def test_txt(self) -> None:
        assert GDriveFileProcessor._get_mime_type(Path("file.txt")) == "text/plain"

    def test_md(self) -> None:
        assert GDriveFileProcessor._get_mime_type(Path("notes.md")) == "text/markdown"

    def test_html(self) -> None:
        assert GDriveFileProcessor._get_mime_type(Path("page.html")) == "text/html"

    def test_htm_same_as_html(self) -> None:
        assert GDriveFileProcessor._get_mime_type(Path("page.htm")) == "text/html"

    def test_unknown_extension(self) -> None:
        assert GDriveFileProcessor._get_mime_type(Path("file.xyz")) == "application/octet-stream"


# ---------------------------------------------------------------------------
# GDriveFileProcessor._needs_processing
# ---------------------------------------------------------------------------


class TestNeedsProcessing:
    @pytest.fixture
    def processor(self, tmp_path: Path) -> GDriveFileProcessor:
        with (
            patch("src.ingestion.gdrive_flow.DoclingClient"),
            patch("src.ingestion.gdrive_flow.GDriveIndexer"),
        ):
            return GDriveFileProcessor(GDriveFlowConfig(sync_dir=str(tmp_path)))

    def test_new_file_needs_processing(
        self, processor: GDriveFileProcessor, tmp_path: Path
    ) -> None:
        path = tmp_path / "new.pdf"
        path.write_bytes(b"content")
        assert processor._needs_processing(path, "unknown_id") is True

    def test_unchanged_file_does_not_need_processing(
        self, processor: GDriveFileProcessor, tmp_path: Path
    ) -> None:
        path = tmp_path / "existing.pdf"
        path.write_bytes(b"content")
        file_id = processor._compute_file_id(path)
        content_hash = processor._compute_content_hash(path)
        from datetime import UTC, datetime

        from src.ingestion.gdrive_flow import ProcessedFile

        processor._processed[file_id] = ProcessedFile(
            file_path="existing.pdf",
            file_id=file_id,
            content_hash=content_hash,
            chunks_count=1,
            processed_at=datetime.now(UTC),
        )
        assert processor._needs_processing(path, file_id) is False

    def test_changed_file_needs_processing(
        self, processor: GDriveFileProcessor, tmp_path: Path
    ) -> None:
        path = tmp_path / "changed.pdf"
        path.write_bytes(b"old content")
        file_id = processor._compute_file_id(path)
        from datetime import UTC, datetime

        from src.ingestion.gdrive_flow import ProcessedFile

        processor._processed[file_id] = ProcessedFile(
            file_path="changed.pdf",
            file_id=file_id,
            content_hash="old_hash_value_xx",
            chunks_count=1,
            processed_at=datetime.now(UTC),
        )
        path.write_bytes(b"new content that is different")
        assert processor._needs_processing(path, file_id) is True


# ---------------------------------------------------------------------------
# ProcessedFile
# ---------------------------------------------------------------------------


class TestProcessedFile:
    def test_creates_with_error(self) -> None:
        from datetime import UTC, datetime

        pf = ProcessedFile(
            file_path="test.pdf",
            file_id="abc123",
            content_hash="hash",
            chunks_count=0,
            processed_at=datetime.now(UTC),
            error="Some error",
        )
        assert pf.error == "Some error"

    def test_creates_without_error(self) -> None:
        from datetime import UTC, datetime

        pf = ProcessedFile(
            file_path="test.pdf",
            file_id="abc123",
            content_hash="hash",
            chunks_count=5,
            processed_at=datetime.now(UTC),
        )
        assert pf.error is None
