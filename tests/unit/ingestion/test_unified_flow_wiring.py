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
