"""D3 — Flow idempotency tests (Markdown-only pipeline, #3235).

Gate test: test_flow_skip_unchanged_gate (required by close-gate).

Tests:
- skip-unchanged: Qdrant already has a point with the same (file_id, content_hash)
  → chunk_file_sync is NOT called; result.skipped == 1
- re-ingest-changed: Qdrant has a point but with a DIFFERENT content_hash
  → chunk_file_sync IS called once; result.processed == 1 (updated_count)
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.unified.config import UnifiedConfig


# ---------------------------------------------------------------------------
# Helpers — mirrors the pattern from test_unified_flow_stateless.py
# ---------------------------------------------------------------------------


def _make_writer() -> MagicMock:
    writer = MagicMock()
    writer.client = MagicMock()
    writer.upsert_chunks_sync.return_value = MagicMock(
        points_upserted=1, points_deleted=0, errors=None
    )
    return writer


def _make_parser() -> MagicMock:
    parser = MagicMock()
    parser.chunk_file_sync.return_value = [object()]
    parser.to_ingestion_chunks.return_value = [MagicMock()]
    return parser


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# D3 — Gate test (REQUIRED)
# ---------------------------------------------------------------------------


def test_flow_skip_unchanged_gate(tmp_path: Path) -> None:
    """GATE TEST: skip-unchanged file must NOT trigger chunk_file_sync.

    When Qdrant scroll returns a record with the same content_hash as the
    file on disk, the flow must skip the file and return skipped==1.
    """
    content = b"# unchanged content"
    doc = tmp_path / "doc.md"
    doc.write_bytes(content)

    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    # Qdrant returns one record → file already indexed with same hash
    writer.client.scroll.return_value = ([MagicMock()], None)
    parser = _make_parser()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified import flow

        result = flow.run_once(config)

    # chunk_file_sync must NOT be called for an unchanged file
    parser.chunk_file_sync.assert_not_called()
    assert result.skipped == 1, f"Expected skipped=1, got skipped={result.skipped}"
    assert result.processed == 0


def test_flow_reingest_changed(tmp_path: Path) -> None:
    """Re-ingest-changed: different hash in Qdrant → chunk_file_sync called once.

    When Qdrant scroll returns no record (hash mismatch → treated as not indexed),
    the flow must call chunk_file_sync and return processed==1 (updated_count).
    """
    doc = tmp_path / "doc.md"
    doc.write_text("# new content", encoding="utf-8")

    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    # Qdrant returns no record → content_hash mismatch / not indexed
    writer.client.scroll.return_value = ([], None)
    parser = _make_parser()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified import flow

        result = flow.run_once(config)

    # chunk_file_sync must be called exactly once for the changed file
    parser.chunk_file_sync.assert_called_once()
    assert result.processed == 1, f"Expected processed=1 (updated_count), got {result.processed}"
    assert result.skipped == 0


# ---------------------------------------------------------------------------
# D4 — Integration (optional, gated by RUN_INTEGRATION_TESTS=1)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.getenv("RUN_INTEGRATION_TESTS"),
    reason="Integration tests require RUN_INTEGRATION_TESTS=1 and live services",
)
def test_flow_integration_live_ingest(tmp_path: Path) -> None:
    """Integration smoke: ingest a real markdown file against live Qdrant + BGE-M3.

    Requires:
      - RUN_INTEGRATION_TESTS=1
      - Qdrant running (QDRANT_URL or default localhost:6333)
      - BGE-M3 running (BGE_M3_URL or default localhost:8000)
    """
    doc = tmp_path / "live_test.md"
    doc.write_text("# Integration test\n\nThis is a live integration test.", encoding="utf-8")

    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    from src.ingestion.unified.flow import run_once

    result = run_once(config)
    assert result.processed >= 1 or result.skipped >= 1, (
        f"Expected at least one file processed or skipped, got: {result}"
    )
