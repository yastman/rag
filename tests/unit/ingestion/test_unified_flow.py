# tests/unit/ingestion/test_unified_flow.py
"""Tests for unified ingestion flow module (CocoIndex orchestration)."""

import hashlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip("cocoindex", reason="cocoindex not installed (ingest extra)")
pytestmark = pytest.mark.requires_extras


class TestComputeFileId:
    """Test compute_file_id: legacy sha256-based file identity."""

    def test_returns_hex_string(self):
        from src.ingestion.unified.flow import compute_file_id

        result = compute_file_id("docs/test.pdf")
        assert isinstance(result, str)
        assert len(result) == 16

    def test_deterministic(self):
        from src.ingestion.unified.flow import compute_file_id

        id1 = compute_file_id("docs/test.pdf")
        id2 = compute_file_id("docs/test.pdf")
        assert id1 == id2

    def test_different_paths_produce_different_ids(self):
        from src.ingestion.unified.flow import compute_file_id

        id1 = compute_file_id("docs/a.pdf")
        id2 = compute_file_id("docs/b.pdf")
        assert id1 != id2

    def test_matches_sha256_prefix(self):
        from src.ingestion.unified.flow import compute_file_id

        path = "docs/test.pdf"
        expected = hashlib.sha256(path.encode()).hexdigest()[:16]
        assert compute_file_id(path) == expected


class TestGetMimeType:
    """Test get_mime_type: extension → MIME mapping."""

    def test_pdf(self):
        from src.ingestion.unified.flow import get_mime_type

        assert get_mime_type("docs/test.pdf") == "application/pdf"

    def test_docx(self):
        from src.ingestion.unified.flow import get_mime_type

        mime = get_mime_type("report.docx")
        assert mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_markdown(self):
        from src.ingestion.unified.flow import get_mime_type

        assert get_mime_type("README.md") == "text/markdown"

    def test_txt(self):
        from src.ingestion.unified.flow import get_mime_type

        assert get_mime_type("notes.txt") == "text/plain"

    def test_html_variants(self):
        from src.ingestion.unified.flow import get_mime_type

        assert get_mime_type("page.html") == "text/html"
        assert get_mime_type("page.htm") == "text/html"

    def test_csv(self):
        from src.ingestion.unified.flow import get_mime_type

        assert get_mime_type("data.csv") == "text/csv"

    def test_unknown_extension_returns_octet_stream(self):
        from src.ingestion.unified.flow import get_mime_type

        assert get_mime_type("file.xyz") == "application/octet-stream"

    def test_case_insensitive(self):
        from src.ingestion.unified.flow import get_mime_type

        assert get_mime_type("DOC.PDF") == "application/pdf"

    def test_nested_path(self):
        from src.ingestion.unified.flow import get_mime_type

        assert get_mime_type("a/b/c/deep.xlsx") == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


class TestFlowNameFor:
    """Test _flow_name_for: deterministic short flow name."""

    def test_starts_with_ingest_prefix(self):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import _flow_name_for

        config = UnifiedConfig(collection_name="test_coll")
        name = _flow_name_for(config)
        assert name.startswith("ingest_")

    def test_deterministic(self):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import _flow_name_for

        c1 = UnifiedConfig(collection_name="my_coll")
        c2 = UnifiedConfig(collection_name="my_coll")
        assert _flow_name_for(c1) == _flow_name_for(c2)

    def test_different_collections_produce_different_names(self):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import _flow_name_for

        c1 = UnifiedConfig(collection_name="coll_a")
        c2 = UnifiedConfig(collection_name="coll_b")
        assert _flow_name_for(c1) != _flow_name_for(c2)

    def test_suffix_is_6_char_hex(self):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import _flow_name_for

        config = UnifiedConfig(collection_name="test")
        name = _flow_name_for(config)
        suffix = name.split("_", 1)[1]
        assert len(suffix) == 6
        int(suffix, 16)  # Should not raise — valid hex


class TestAppNamespaceFor:
    """Test _app_namespace_for: always returns 'unified'."""

    def test_returns_unified(self):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import _app_namespace_for

        config = UnifiedConfig(collection_name="anything")
        assert _app_namespace_for(config) == "unified"

    def test_independent_of_collection(self):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import _app_namespace_for

        c1 = UnifiedConfig(collection_name="a")
        c2 = UnifiedConfig(collection_name="b")
        assert _app_namespace_for(c1) == _app_namespace_for(c2)


class TestFileIdFromContent:
    """Test file_id_from_content: manifest-based identity."""

    def test_falls_back_when_manifest_is_none(self):
        """When _manifest is None, falls back to path-based id."""
        import src.ingestion.unified.flow as flow_module

        original = flow_module._manifest
        try:
            flow_module._manifest = None
            result = flow_module.file_id_from_content("test.pdf", b"content")
            expected = flow_module.compute_file_id("test.pdf")
            assert result == expected
        finally:
            flow_module._manifest = original

    def test_falls_back_when_content_is_none(self):
        """When content is None, falls back to path-based id."""
        import src.ingestion.unified.flow as flow_module

        original = flow_module._manifest
        try:
            flow_module._manifest = MagicMock()
            result = flow_module.file_id_from_content("test.pdf", None)
            expected = flow_module.compute_file_id("test.pdf")
            assert result == expected
        finally:
            flow_module._manifest = original

    def test_uses_manifest_when_available(self):
        """When manifest exists and content is provided, uses manifest."""
        import src.ingestion.unified.flow as flow_module

        original = flow_module._manifest
        mock_manifest = MagicMock()
        mock_manifest.get_or_create_id.return_value = "stable_uuid_123"
        try:
            flow_module._manifest = mock_manifest
            result = flow_module.file_id_from_content("test.pdf", b"content")
            assert result == "stable_uuid_123"
            mock_manifest.get_or_create_id.assert_called_once()
        finally:
            flow_module._manifest = original


class TestMimeTypeFromFilename:
    """Test mime_type_from_filename CocoIndex function."""

    def test_returns_correct_mime(self):
        from src.ingestion.unified.flow import mime_type_from_filename

        result = mime_type_from_filename("report.pdf")
        assert result == "application/pdf"


class TestFileSizeFromBytes:
    """Test file_size_from_bytes CocoIndex function."""

    def test_returns_length(self):
        from src.ingestion.unified.flow import file_size_from_bytes

        assert file_size_from_bytes(b"hello") == 5

    def test_returns_zero_for_none(self):
        from src.ingestion.unified.flow import file_size_from_bytes

        assert file_size_from_bytes(None) == 0

    def test_returns_zero_for_empty(self):
        from src.ingestion.unified.flow import file_size_from_bytes

        assert file_size_from_bytes(b"") == 0


class TestBasenameFromFilename:
    """Test basename_from_filename CocoIndex function."""

    def test_extracts_basename(self):
        from src.ingestion.unified.flow import basename_from_filename

        assert basename_from_filename("docs/sub/report.pdf") == "report.pdf"

    def test_simple_filename(self):
        from src.ingestion.unified.flow import basename_from_filename

        assert basename_from_filename("file.txt") == "file.txt"


class TestAbsPathFromFilename:
    """Test abs_path_from_filename CocoIndex function."""

    def test_joins_sync_dir_and_filename(self):
        import src.ingestion.unified.flow as flow_module

        original = flow_module._current_sync_dir
        try:
            flow_module._current_sync_dir = "/opt/rag-fresh/drive-sync"
            result = flow_module.abs_path_from_filename("docs/test.pdf")
            assert result == "/opt/rag-fresh/drive-sync/docs/test.pdf"
        finally:
            flow_module._current_sync_dir = original

    def test_empty_sync_dir(self):
        import src.ingestion.unified.flow as flow_module

        original = flow_module._current_sync_dir
        try:
            flow_module._current_sync_dir = ""
            result = flow_module.abs_path_from_filename("test.pdf")
            assert result == "test.pdf"
        finally:
            flow_module._current_sync_dir = original


class TestMimeTypesConstant:
    """Test MIME_TYPES dictionary coverage."""

    def test_all_supported_extensions_have_mime(self):
        from src.ingestion.unified.flow import MIME_TYPES

        expected = {
            ".pdf",
            ".docx",
            ".doc",
            ".xlsx",
            ".pptx",
            ".md",
            ".txt",
            ".html",
            ".htm",
            ".csv",
        }
        assert set(MIME_TYPES.keys()) == expected

    def test_no_empty_values(self):
        from src.ingestion.unified.flow import MIME_TYPES

        for ext, mime in MIME_TYPES.items():
            assert mime, f"Empty MIME for {ext}"


class TestBuildFlow:
    """Test build_flow: CocoIndex flow construction."""

    @patch("cocoindex.init")
    @patch("src.ingestion.unified.flow.flow_names", return_value=[])
    @patch("cocoindex.open_flow")
    @patch("src.ingestion.unified.flow.GDriveManifest")
    def test_initializes_manifest(self, mock_manifest_cls, mock_open, mock_names, mock_init):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import build_flow

        config = UnifiedConfig(sync_dir=Path("/tmp/test-sync"))
        build_flow(config)

        mock_manifest_cls.assert_called_once_with(Path("/tmp/test-sync"))

    @patch("cocoindex.init")
    @patch("src.ingestion.unified.flow.flow_names", return_value=[])
    @patch("cocoindex.open_flow")
    @patch("src.ingestion.unified.flow.GDriveManifest")
    def test_calls_cocoindex_init_with_settings(
        self, mock_manifest, mock_open, mock_names, mock_init
    ):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import build_flow

        config = UnifiedConfig(
            database_url="postgresql://user:pass@db:5432/coco",
            collection_name="test_coll",
        )
        build_flow(config)

        mock_init.assert_called_once()
        settings = mock_init.call_args[0][0]
        assert settings.database.url == "postgresql://user:pass@db:5432/coco"
        assert settings.app_namespace == "unified"

    @patch("cocoindex.init")
    @patch("src.ingestion.unified.flow.flow_names", return_value=[])
    @patch("cocoindex.open_flow")
    @patch("src.ingestion.unified.flow.GDriveManifest")
    def test_opens_flow_with_correct_name(self, mock_manifest, mock_open, mock_names, mock_init):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import _flow_name_for, build_flow

        config = UnifiedConfig(collection_name="test_coll")
        build_flow(config)

        expected_name = _flow_name_for(config)
        mock_open.assert_called_once()
        assert mock_open.call_args[0][0] == expected_name

    @patch("cocoindex.init")
    @patch("src.ingestion.unified.flow.flow_names")
    @patch("src.ingestion.unified.flow.flow_by_name")
    @patch("cocoindex.open_flow")
    @patch("src.ingestion.unified.flow.GDriveManifest")
    def test_closes_existing_flow_if_name_exists(
        self, mock_manifest, mock_open, mock_flow_by_name, mock_names, mock_init
    ):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import _flow_name_for, build_flow

        config = UnifiedConfig(collection_name="test_coll")
        flow_name = _flow_name_for(config)
        mock_names.return_value = [flow_name]
        mock_existing_flow = MagicMock()
        mock_flow_by_name.return_value = mock_existing_flow

        build_flow(config)

        mock_flow_by_name.assert_called_once_with(flow_name)
        mock_existing_flow.close.assert_called_once()

    @patch("cocoindex.init")
    @patch("src.ingestion.unified.flow.flow_names", return_value=[])
    @patch("cocoindex.open_flow")
    @patch("src.ingestion.unified.flow.GDriveManifest")
    def test_uses_default_config_when_none(self, mock_manifest, mock_open, mock_names, mock_init):
        from src.ingestion.unified.flow import build_flow

        build_flow(None)

        mock_init.assert_called_once()
        mock_open.assert_called_once()


class TestRunOnce:
    """Test run_once: single-pass ingestion."""

    @patch("src.ingestion.unified.flow.build_flow")
    def test_calls_setup_update_close(self, mock_build):
        from src.ingestion.unified.flow import run_once

        mock_flow = MagicMock()
        mock_build.return_value = mock_flow

        run_once()

        mock_flow.setup.assert_called_once()
        mock_flow.update.assert_called_once_with(print_stats=True)
        mock_flow.close.assert_called_once()

    @patch("src.ingestion.unified.flow.build_flow")
    def test_passes_config_to_build(self, mock_build):
        from src.ingestion.unified.config import UnifiedConfig
        from src.ingestion.unified.flow import run_once

        mock_build.return_value = MagicMock()
        config = UnifiedConfig(collection_name="custom")

        run_once(config)

        mock_build.assert_called_once_with(config)


class TestRunWatch:
    """Test run_watch: continuous ingestion mode."""

    @patch("src.ingestion.unified.flow.build_flow")
    @patch("cocoindex.FlowLiveUpdater")
    def test_starts_live_updater(self, mock_updater_cls, mock_build):
        from src.ingestion.unified.flow import run_watch

        mock_flow = MagicMock()
        mock_build.return_value = mock_flow
        mock_updater = MagicMock()
        mock_updater.__enter__ = MagicMock(return_value=mock_updater)
        mock_updater.__exit__ = MagicMock(return_value=False)
        mock_updater_cls.return_value = mock_updater

        run_watch()

        mock_flow.setup.assert_called_once()
        mock_updater.wait.assert_called_once()
        mock_flow.close.assert_called_once()

    @patch("src.ingestion.unified.flow.build_flow")
    @patch("cocoindex.FlowLiveUpdater")
    def test_handles_keyboard_interrupt(self, mock_updater_cls, mock_build):
        from src.ingestion.unified.flow import run_watch

        mock_flow = MagicMock()
        mock_build.return_value = mock_flow
        mock_updater = MagicMock()
        mock_updater.__enter__ = MagicMock(return_value=mock_updater)
        mock_updater.__exit__ = MagicMock(return_value=False)
        mock_updater.wait.side_effect = KeyboardInterrupt
        mock_updater_cls.return_value = mock_updater

        # Should not raise
        run_watch()

        mock_flow.close.assert_called_once()

    @patch("src.ingestion.unified.flow.build_flow")
    @patch("cocoindex.FlowLiveUpdater")
    def test_uses_default_config_when_none(self, mock_updater_cls, mock_build):
        from src.ingestion.unified.flow import run_watch

        mock_flow = MagicMock()
        mock_build.return_value = mock_flow
        mock_updater = MagicMock()
        mock_updater.__enter__ = MagicMock(return_value=mock_updater)
        mock_updater.__exit__ = MagicMock(return_value=False)
        mock_updater_cls.return_value = mock_updater

        run_watch(None)

        mock_build.assert_called_once()
