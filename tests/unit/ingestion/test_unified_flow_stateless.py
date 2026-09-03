"""Behaviour tests for the stateless unified ingestion flow.

``run_once`` must scan ``sync_dir``, parse+embed+upsert each supported file,
and skip files whose ``(file_id, content_hash)`` already has a point in
Qdrant — with no external state database.
"""

from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from unittest.mock import MagicMock, patch

from src.ingestion.unified.config import UnifiedConfig


def _make_writer() -> MagicMock:
    writer = MagicMock()
    writer.client = MagicMock()
    writer.upsert_chunks_sync.return_value = MagicMock(
        points_upserted=3, points_deleted=0, errors=None
    )
    return writer


def _make_parser() -> MagicMock:
    parser = MagicMock()
    parser.chunk_file_sync.return_value = [object()]
    parser.to_ingestion_chunks.return_value = [MagicMock()]
    return parser


def test_run_once_ingests_new_file(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("# hello", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.return_value = ([], None)  # nothing indexed yet
    parser = _make_parser()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    parser.chunk_file_sync.assert_called_once()
    writer.upsert_chunks_sync.assert_called_once()
    assert result.processed == 1
    assert result.skipped == 0


def test_run_once_skips_already_indexed_file(tmp_path: Path) -> None:
    (tmp_path / "doc.md").write_text("# hello", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.return_value = ([MagicMock()], None)  # already indexed
    parser = _make_parser()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    parser.chunk_file_sync.assert_not_called()
    writer.upsert_chunks_sync.assert_not_called()
    assert result.processed == 0
    assert result.skipped == 1


def test_run_once_ignores_unsupported_extensions(tmp_path: Path) -> None:
    (tmp_path / "skip.bin").write_bytes(b"\x00\x01")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.return_value = ([], None)
    parser = _make_parser()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    parser.chunk_file_sync.assert_not_called()
    assert result.processed == 0
    assert result.skipped == 0


def test_modified_file_replaces_before_removing_old_chunks(tmp_path: Path) -> None:
    """A successful replacement removes only prior ids after the new upsert."""
    (tmp_path / "doc.md").write_text("# changed", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.side_effect = [
        ([], None),
        ([{"payload": {"metadata": {"file_id": "old-file-id"}}}], None),
    ]
    order: list[str] = []
    writer.upsert_chunks_sync.side_effect = lambda *_a, **_k: (
        order.append("upsert") or MagicMock(points_upserted=3, points_deleted=0, errors=None)
    )
    writer.delete_file_sync.side_effect = lambda **kwargs: order.append(
        f"delete:{kwargs['file_id']}"
    )
    parser = _make_parser()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    new_file_id = writer.upsert_chunks_sync.call_args.kwargs["file_id"]
    writer.delete_file_sync.assert_called_once_with(
        file_id="old-file-id", collection_name=config.collection_name
    )
    assert new_file_id != "old-file-id"
    assert order == ["upsert", "delete:old-file-id"]
    assert result.processed == 1


def test_modified_file_keeps_old_chunks_when_replacement_fails(tmp_path: Path) -> None:
    """Embedding or upsert failure must not erase the prior searchable version."""
    (tmp_path / "doc.md").write_text("# changed", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.side_effect = [
        ([], None),
        ([{"payload": {"metadata": {"file_id": "old-file-id"}}}], None),
    ]
    writer.upsert_chunks_sync.return_value = MagicMock(
        points_upserted=0, points_deleted=0, errors=["BGE-M3 unavailable"]
    )
    parser = _make_parser()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    writer.delete_file_sync.assert_not_called()
    assert result.errors == 1


def test_concurrent_replacements_serialize_same_source(tmp_path: Path) -> None:
    """The next replacement cannot sweep another replacement before it lands."""
    from src.ingestion.unified.flow import _ingest_directory

    first_dir, second_dir = tmp_path / "first", tmp_path / "second"
    first_dir.mkdir()
    second_dir.mkdir()
    (first_dir / "doc.md").write_text("first", encoding="utf-8")
    (second_dir / "doc.md").write_text("second", encoding="utf-8")
    first_config = UnifiedConfig(sync_dir=first_dir, manifest_dir=first_dir)
    second_config = UnifiedConfig(sync_dir=second_dir, manifest_dir=second_dir)
    writer = _make_writer()
    first_upsert_started, release_first_upsert = Event(), Event()
    written_ids: set[str] = set()
    events: list[tuple[str, str]] = []

    def scroll(**kwargs: object) -> tuple[list[dict[str, object]], None]:
        if not kwargs["with_payload"]:
            return [], None
        return [
            {"payload": {"metadata": {"file_id": file_id}}}
            for file_id in {"old-file-id", *written_ids}
        ], None

    def upsert(**kwargs: object) -> MagicMock:
        file_id = str(kwargs["file_id"])
        events.append(("upsert", file_id))
        if not first_upsert_started.is_set():
            first_upsert_started.set()
            assert release_first_upsert.wait(timeout=5)
        written_ids.add(file_id)
        return MagicMock(points_upserted=1, points_deleted=0, errors=None)

    writer.client.scroll.side_effect = scroll
    writer.upsert_chunks_sync.side_effect = upsert
    writer.delete_file_sync.side_effect = lambda **kwargs: events.append(
        ("delete", str(kwargs["file_id"]))
    )
    parser = _make_parser()

    with (
        patch("src.ingestion.unified.flow._already_indexed", return_value=False),
        patch(
            "src.ingestion.unified.flow.file_id_from_content",
            side_effect=lambda _name, content: f"new-{content.decode()}",
        ),
    ):
        first = Thread(target=_ingest_directory, args=(first_config, writer, parser))
        first.start()
        assert first_upsert_started.wait(timeout=5)
        second = Thread(target=_ingest_directory, args=(second_config, writer, parser))
        second.start()
        release_first_upsert.set()
        first.join(timeout=5)
        second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert events.index(("upsert", "new-first")) < events.index(("upsert", "new-second"))
    assert events.index(("upsert", "new-second")) < events.index(("delete", "new-first"))


def test_run_once_passes_content_hash_to_payload(tmp_path: Path) -> None:
    """The content_hash dedup key must be written into the Qdrant payload."""
    (tmp_path / "doc.md").write_text("# hello", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.return_value = ([], None)
    parser = _make_parser()

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        run_once(config)

    kwargs = writer.upsert_chunks_sync.call_args.kwargs
    assert kwargs["file_metadata"]["content_hash"]
