"""Focused wiring tests for unified ingestion flow."""

from __future__ import annotations

from unittest.mock import MagicMock


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


def test_build_flow_does_not_exist() -> None:
    """build_flow was removed with CocoIndex (#2834); ensure it is gone."""
    import src.ingestion.unified.flow as flow_module

    assert not hasattr(flow_module, "build_flow"), (
        "build_flow should not exist after CocoIndex removal (#2834)"
    )
