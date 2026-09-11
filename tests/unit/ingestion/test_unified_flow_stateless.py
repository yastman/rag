"""Behaviour tests for the stateless unified ingestion flow.

Single unit owner for flow behavior (#3407): ``run_once`` must scan
``sync_dir``, parse+embed+upsert each supported file, and skip files whose
``(file_id, content_hash, source)`` already has a point in Qdrant — with no
external state database. Manifest paths are reconciled against the live scan
listing before identity allocation (#3369), so a renamed file reuses its
identity and a copy stays distinct. Live-service flow scenarios belong to the
strict E2E suite (#3416), not this unit lane.
"""

from __future__ import annotations

from pathlib import Path
from threading import Event, Thread
from typing import Any
from unittest.mock import MagicMock, patch

from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.manifest import compute_content_hash_from_bytes


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


class _FakeQdrantPoints:
    """In-memory stand-in for Qdrant points keyed by deterministic point ids.

    Mirrors ``QdrantHybridWriter.generate_point_id``: point identity is
    ``(file_id, chunk_index)``, so re-upserting the same file_id overwrites
    the points in place — the payload (including ``metadata.source``) moves
    to the new path without deleting or re-creating the points. Scroll
    answers honour the filter conditions, including ``metadata.source``.
    """

    def __init__(self) -> None:
        self.points: dict[tuple[str, int], dict[str, str]] = {}

    def commit(
        self, *, file_id: str, source_path: str, content_hash: str, chunks: int
    ) -> MagicMock:
        for i in range(chunks):
            self.points[(file_id, i)] = {
                "file_id": file_id,
                "content_hash": content_hash,
                "source": source_path,
            }
        return MagicMock(points_upserted=chunks, points_deleted=0, errors=None)

    def scroll(self, **kwargs: Any) -> tuple[list[Any], None]:
        flt = kwargs["scroll_filter"]
        conditions = {
            condition.key.split(".", 1)[-1]: condition.match.value  # metadata.file_id → file_id
            for condition in flt.must
        }
        if not kwargs.get("with_payload"):
            # Dedup query: any point satisfying every condition.
            for record in self.points.values():
                if all(record.get(key) == value for key, value in conditions.items()):
                    return [[MagicMock()], None]
            return [[], None]
        # Source snapshot query: file ids stored under one source path.
        source = conditions["source"]
        matching = [
            {"payload": {"metadata": {"file_id": record["file_id"]}}}
            for record in self.points.values()
            if record["source"] == source
        ]
        return [matching, None]

    def sources(self) -> set[str]:
        return {record["source"] for record in self.points.values()}

    def file_ids(self) -> set[str]:
        return {record["file_id"] for record in self.points.values()}


def _make_store_writer(store: _FakeQdrantPoints) -> MagicMock:
    writer = _make_writer()
    writer.client = MagicMock()
    writer.client.scroll.side_effect = store.scroll

    def upsert(**kwargs: Any) -> MagicMock:
        return store.commit(
            file_id=kwargs["file_id"],
            source_path=kwargs["source_path"],
            content_hash=kwargs["file_metadata"]["content_hash"],
            chunks=len(kwargs["chunks"]),
        )

    writer.upsert_chunks_sync.side_effect = upsert
    return writer


def _run_once(config: UnifiedConfig, writer: MagicMock, parser: MagicMock):
    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        return run_once(config)


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


def test_changed_file_becoming_empty_removes_prior_points(tmp_path: Path) -> None:
    """Nonempty-to-empty commits an empty replacement (#3370).

    A successful parse yielding zero chunks is an empty success, not a skip:
    the prior searchable generation for this source must be removed, otherwise
    stale points stay queryable forever.
    """
    (tmp_path / "doc.md").write_text("", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.side_effect = [
        ([], None),  # _already_indexed: the empty content has no point yet
        ([{"payload": {"metadata": {"file_id": "old-file-id"}}}], None),  # source snapshot
    ]
    parser = MagicMock()
    parser.chunk_file_sync.return_value = []  # empty-but-successful parse
    parser.to_ingestion_chunks.return_value = []

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    writer.upsert_chunks_sync.assert_not_called()
    writer.delete_file_sync.assert_called_once_with(
        file_id="old-file-id", collection_name=config.collection_name
    )
    assert result.processed == 1
    assert result.errors == 0


def test_parse_failure_keeps_old_points_and_reports_error(tmp_path: Path) -> None:
    """A parse/read failure is non-destructive (#3370).

    When the parser raises (unreadable bytes, missing file), the flow must not
    delete anything: the last-good points stay searchable and the pass records
    an error.
    """
    (tmp_path / "doc.md").write_text("# changed", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.side_effect = [
        ([], None),  # dedup miss: content changed
        ([{"payload": {"metadata": {"file_id": "old-file-id"}}}], None),
    ]
    parser = MagicMock()
    parser.chunk_file_sync.side_effect = UnicodeDecodeError(
        "utf-8", b"\xff", 0, 1, "invalid start byte"
    )

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        result = run_once(config)

    writer.upsert_chunks_sync.assert_not_called()
    writer.delete_file_sync.assert_not_called()
    assert result.errors == 1


def test_repeated_empty_replacement_is_idempotent(tmp_path: Path) -> None:
    """A repeated empty replacement deletes nothing further and never errors (#3370).

    After the first empty replacement the collection holds no points for the
    source, so a second pass must be a no-op mutation with a clean result.
    """
    (tmp_path / "doc.md").write_text("", encoding="utf-8")
    config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
    writer = _make_writer()
    writer.client.scroll.side_effect = [
        ([], None),  # pass 1: dedup miss
        ([{"payload": {"metadata": {"file_id": "old-file-id"}}}], None),  # pass 1 snapshot
        ([], None),  # pass 2: dedup miss
        ([], None),  # pass 2 snapshot: collection emptied by pass 1
    ]
    parser = MagicMock()
    parser.chunk_file_sync.return_value = []
    parser.to_ingestion_chunks.return_value = []

    with (
        patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
        patch("src.ingestion.unified.flow._make_parser", return_value=parser),
    ):
        from src.ingestion.unified.flow import run_once

        first = run_once(config)
        second = run_once(config)

    assert first.errors == 0
    assert second.errors == 0
    writer.delete_file_sync.assert_called_once_with(
        file_id="old-file-id", collection_name=config.collection_name
    )


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


class TestManifestPathReconciliation:
    """Manifest paths reconcile against the live scan (#3369).

    Rename (A.md -> B.md, unchanged bytes) preserves the point identity and
    removes the old searchable path; a copy (A.md + B.md) keeps a distinct
    identity; an interrupted scan preserves the last-good state.
    """

    CONTENT = "# same content"

    def test_rename_reuses_file_id_and_replaces_old_searchable_path(self, tmp_path: Path) -> None:
        """A.md -> B.md with unchanged content keeps the file_id and point ids.

        The pass must re-index under the new path (metadata.source moves) and
        the old path must stop being searchable — without a delete+recreate
        churn of the file's points.
        """
        (tmp_path / "A.md").write_text(self.CONTENT, encoding="utf-8")
        config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
        store = _FakeQdrantPoints()
        writer = _make_store_writer(store)
        parser = _make_parser()

        first = _run_once(config, writer, parser)
        original_file_id = writer.upsert_chunks_sync.call_args.kwargs["file_id"]
        assert first.processed == 1
        assert store.sources() == {"A.md"}

        (tmp_path / "A.md").rename(tmp_path / "B.md")
        point_ids_before = set(store.points)
        writer.upsert_chunks_sync.reset_mock()

        second = _run_once(config, writer, parser)

        kwargs = writer.upsert_chunks_sync.call_args.kwargs
        assert kwargs["file_id"] == original_file_id, (
            "A rename must reuse the original file_id, not mint a new one."
        )
        assert kwargs["source_path"] == "B.md"
        assert not writer.delete_file_sync.called, (
            "Rename re-index must not delete+recreate the file's points."
        )
        assert set(store.points) == point_ids_before, (
            "Point ids are deterministic on (file_id, chunk): the rename must "
            "replace points in place, not churn identity."
        )
        assert store.sources() == {"B.md"}, (
            "The old path must no longer be searchable after the rename."
        )
        assert second.processed == 1
        assert second.skipped == 0

    def test_copy_gets_distinct_file_id(self, tmp_path: Path) -> None:
        """A.md + B.md with identical content keep distinct file_ids."""
        (tmp_path / "A.md").write_text(self.CONTENT, encoding="utf-8")
        config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
        store = _FakeQdrantPoints()
        writer = _make_store_writer(store)
        parser = _make_parser()

        _run_once(config, writer, parser)
        original_file_id = writer.upsert_chunks_sync.call_args.kwargs["file_id"]

        (tmp_path / "B.md").write_text(self.CONTENT, encoding="utf-8")
        writer.upsert_chunks_sync.reset_mock()

        second = _run_once(config, writer, parser)

        kwargs = writer.upsert_chunks_sync.call_args.kwargs
        copy_file_id = kwargs["file_id"]
        assert copy_file_id != original_file_id, (
            "A copy at a new path while the original is active must receive its own file_id."
        )
        assert kwargs["source_path"] == "B.md"
        assert store.file_ids() == {original_file_id, copy_file_id}
        assert store.sources() == {"A.md", "B.md"}
        assert second.processed == 1
        assert second.skipped == 1, "The original A.md must still be skipped as unchanged."

    def test_interrupted_scan_preserves_last_good_state(self, tmp_path: Path) -> None:
        """A failed pass after a rename keeps the old points and heals next run."""
        (tmp_path / "A.md").write_text(self.CONTENT, encoding="utf-8")
        config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)
        store = _FakeQdrantPoints()
        writer = _make_store_writer(store)
        parser = _make_parser()

        _run_once(config, writer, parser)
        original_file_id = writer.upsert_chunks_sync.call_args.kwargs["file_id"]
        content_hash = compute_content_hash_from_bytes(self.CONTENT.encode("utf-8"))

        (tmp_path / "A.md").rename(tmp_path / "B.md")
        writer.upsert_chunks_sync.side_effect = lambda **_kwargs: MagicMock(
            points_upserted=0, points_deleted=0, errors=["BGE-M3 unavailable"]
        )

        interrupted = _run_once(config, writer, parser)

        assert interrupted.errors == 1
        writer.delete_file_sync.assert_not_called()
        assert store.sources() == {"A.md"}, (
            "The interrupted scan must leave the last-good searchable points intact."
        )

        from src.ingestion.unified.manifest import FileManifest

        manifest = FileManifest(config.effective_manifest_dir())
        assert "A.md" not in manifest._path_to_hash
        assert manifest._hash_to_id[content_hash] == original_file_id, (
            "The identity anchor must survive the interrupted scan."
        )

        # Next healthy pass heals the rename onto the preserved identity.
        writer = _make_store_writer(store)
        healed = _run_once(config, writer, parser)

        kwargs = writer.upsert_chunks_sync.call_args.kwargs
        assert healed.errors == 0
        assert kwargs["file_id"] == original_file_id
        assert kwargs["source_path"] == "B.md"
        assert store.sources() == {"B.md"}

    def test_reconciliation_precedes_identity_allocation(self, tmp_path: Path) -> None:
        """_ingest_directory reconciles paths before allocating any identity."""
        import src.ingestion.unified.flow as flow_module

        (tmp_path / "a.md").write_text("alpha", encoding="utf-8")
        (tmp_path / "ignore.txt").write_text("skip", encoding="utf-8")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "b.md").write_text("beta", encoding="utf-8")
        config = UnifiedConfig(sync_dir=tmp_path, manifest_dir=tmp_path)

        calls: list[tuple[str, object]] = []
        manifest = MagicMock()
        manifest.reconcile_paths.side_effect = lambda active_paths: calls.append(
            ("reconcile", set(active_paths))
        )
        manifest.get_or_create_id.side_effect = lambda path, _hash: (
            calls.append(("id", path)) or f"fid-{path}"
        )

        writer = _make_writer()
        writer.client.scroll.return_value = ([], None)
        parser = _make_parser()

        with (
            patch("src.ingestion.unified.flow.QdrantHybridWriter", return_value=writer),
            patch("src.ingestion.unified.flow._make_parser", return_value=parser),
            patch.object(flow_module, "_manifest", manifest),
        ):
            flow_module._ingest_directory(config, writer, parser)

        assert calls[0] == (
            "reconcile",
            {"a.md", str((sub / "b.md").relative_to(tmp_path))},
        ), (
            "Reconciliation must run once per scan with the active supported "
            "paths, before any identity allocation."
        )
        assert calls[1:] == [
            ("id", "a.md"),
            ("id", str((sub / "b.md").relative_to(tmp_path))),
        ]


def test_file_id_from_content_passes_content_hash_to_manifest() -> None:
    """flow.file_id_from_content delegates identity to the manifest with the content hash."""
    import src.ingestion.unified.flow as flow_module

    original = flow_module._manifest
    manifest = MagicMock()
    manifest.get_or_create_id.return_value = "stable-id"

    try:
        flow_module._manifest = manifest
        result = flow_module.file_id_from_content("docs/a.md", b"payload")
    finally:
        flow_module._manifest = original

    assert result == "stable-id"
    manifest.get_or_create_id.assert_called_once_with(
        "docs/a.md",
        compute_content_hash_from_bytes(b"payload"),
    )
