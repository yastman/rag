"""Behaviour tests for the stateless unified ingestion flow.

``run_once`` must scan ``sync_dir``, parse+embed+upsert each supported file,
and skip files whose ``(file_id, content_hash)`` already has a point in
Qdrant — with no external state database.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from src.ingestion.unified.config import UnifiedConfig


def _make_writer() -> MagicMock:
    writer = MagicMock()
    writer.client = MagicMock()
    writer.upsert_chunks_sync.return_value = MagicMock(
        points_upserted=3, points_deleted=0, errors=None
    )
    return writer


def _make_docling() -> MagicMock:
    docling = MagicMock()
    docling.chunk_file_sync.return_value = [object()]
    docling.to_ingestion_chunks.return_value = [MagicMock()]
    return docling


def test_run_once_ingests_new_file(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("# hello", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.return_value = ([], None)  # nothing indexed yet
    docling = _make_docling()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_docling", return_value=docling),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    docling.chunk_file_sync.assert_called_once()
    writer.upsert_chunks_sync.assert_called_once()
    assert result.processed == 1
    assert result.skipped == 0


def test_run_once_skips_already_indexed_file(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("# hello", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.return_value = ([MagicMock()], None)  # already indexed
    docling = _make_docling()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_docling", return_value=docling),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    docling.chunk_file_sync.assert_not_called()
    writer.upsert_chunks_sync.assert_not_called()
    assert result.processed == 0
    assert result.skipped == 1


def test_run_once_ignores_unsupported_extensions(tmp_path: Path) -> None:
    (tmp_path / "skip.bin").write_bytes(b"\x00\x01")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.return_value = ([], None)
    docling = _make_docling()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_docling", return_value=docling),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    docling.chunk_file_sync.assert_not_called()
    assert result.processed == 0
    assert result.skipped == 0


def test_modified_file_deletes_old_chunks(tmp_path: Path) -> None:
    """A new/changed file must sweep prior points by source_path before upsert.

    ``file_id`` is re-minted when content changes (manifest), so the old
    version's points live under a *different* ``file_id`` and the post-upsert
    stale sweep can't reach them. Deleting by the stable ``source_path`` before
    upsert is what prevents orphaned stale chunks.
    """
    (tmp_path / "doc.md").write_text("# changed", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.return_value = ([], None)  # not indexed → (re)ingest

    order: list[str] = []
    writer.delete_by_source_path_sync.side_effect = lambda *_a, **_k: order.append("delete")
    writer.upsert_chunks_sync.side_effect = lambda *_a, **_k: (
        order.append("upsert") or MagicMock(points_upserted=3, points_deleted=0, errors=None)
    )
    docling = _make_docling()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_docling", return_value=docling),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    writer.delete_by_source_path_sync.assert_called_once()
    assert writer.delete_by_source_path_sync.call_args.kwargs["source_path"] == "doc.md"
    assert order == ["delete", "upsert"], "stale points must be swept before upsert"
    assert result.processed == 1


def test_run_once_passes_content_hash_to_payload(tmp_path: Path) -> None:
    """The content_hash dedup key must be written into the Qdrant payload."""
    (tmp_path / "doc.md").write_text("# hello", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.return_value = ([], None)
    docling = _make_docling()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_docling", return_value=docling),
    ):
        from src.ingestion.unified.flow import run_once

        run_once(config)

    kwargs = writer.upsert_chunks_sync.call_args.kwargs
    assert kwargs["file_metadata"]["content_hash"]
