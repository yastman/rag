"""Focused wiring tests for unified ingestion flow."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


pytestmark = [
    pytest.mark.requires_extras,
    pytest.mark.skipif(
        importlib.util.find_spec("cocoindex") is None,
        reason="cocoindex not installed (ingest extra)",
    ),
]


def test_build_flow_uses_effective_manifest_dir(tmp_path: Path) -> None:
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.flow import build_flow

    sync_dir = tmp_path / "sync"
    manifest_dir = tmp_path / "manifest"
    config = UnifiedConfig(sync_dir=sync_dir, manifest_dir=manifest_dir)

    with (
        patch("cocoindex.init"),
        patch("src.ingestion.unified.flow.flow_names", return_value=[]),
        patch("cocoindex.open_flow", return_value=MagicMock()),
        patch("src.ingestion.unified.flow.GDriveManifest") as manifest_cls,
    ):
        build_flow(config)

    manifest_cls.assert_called_once_with(manifest_dir)
    assert manifest_dir.exists()


def test_file_id_from_content_passes_content_hash_to_manifest() -> None:
    import src.ingestion.unified.flow as flow_module
    from src.ingestion.unified.manifest import compute_content_hash_from_bytes

    original = flow_module._manifest
    manifest = MagicMock()
    manifest.get_or_create_id.return_value = "stable-id"

    try:
        flow_module._manifest = manifest
        result = flow_module.file_id_from_content("docs/a.pdf", b"payload")
    finally:
        flow_module._manifest = original

    assert result == "stable-id"
    manifest.get_or_create_id.assert_called_once_with(
        "docs/a.pdf",
        compute_content_hash_from_bytes(b"payload"),
    )


def test_build_flow_closes_existing_registered_flow(tmp_path: Path) -> None:
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.flow import _flow_name_for, build_flow

    config = UnifiedConfig(sync_dir=tmp_path, collection_name="existing_collection")
    flow_name = _flow_name_for(config)
    existing_flow = MagicMock()

    with (
        patch("cocoindex.init"),
        patch("src.ingestion.unified.flow.flow_names", return_value=[flow_name]),
        patch("src.ingestion.unified.flow.flow_by_name", return_value=existing_flow) as by_name,
        patch("cocoindex.open_flow", return_value=MagicMock()),
        patch("src.ingestion.unified.flow.GDriveManifest"),
    ):
        build_flow(config)

    by_name.assert_called_once_with(flow_name)
    existing_flow.close.assert_called_once()


def test_run_once_records_error_status_and_closes_flow() -> None:
    from src.ingestion.unified.flow import run_once

    flow = MagicMock()
    flow.update.side_effect = RuntimeError("boom")

    with (
        patch("src.ingestion.unified.flow.build_flow", return_value=flow),
        patch("src.ingestion.unified.flow.try_update_ingestion_trace") as update_trace,
    ):
        with pytest.raises(RuntimeError, match="boom"):
            run_once()

    flow.setup.assert_called_once()
    flow.update.assert_called_once_with(print_stats=True)
    flow.close.assert_called_once()
    assert update_trace.call_args_list[0].kwargs == {
        "command": "flow-run-once",
        "status": "started",
    }
    assert update_trace.call_args_list[1].kwargs == {
        "command": "flow-run-once",
        "status": "error",
        "metadata": {"error_type": "RuntimeError"},
    }


def test_run_once_records_completed_status_after_success() -> None:
    from src.ingestion.unified.flow import run_once

    flow = MagicMock()

    with (
        patch("src.ingestion.unified.flow.build_flow", return_value=flow),
        patch("src.ingestion.unified.flow.try_update_ingestion_trace") as update_trace,
    ):
        run_once()

    flow.close.assert_called_once()
    assert update_trace.call_args_list[-1].kwargs == {
        "command": "flow-run-once",
        "status": "completed",
    }
