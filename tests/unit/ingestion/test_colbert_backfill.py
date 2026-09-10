"""Unit tests for ColBERT backfill runner and CLI command wiring."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _record(
    point_id: int | str,
    *,
    page_content: str | None = None,
    text: str | None = None,
    colbert: list[list[float]] | None = None,
):
    payload = {}
    if page_content is not None:
        payload["page_content"] = page_content
    if text is not None:
        payload["text"] = text

    vector = {}
    if colbert is not None:
        vector["colbert"] = colbert

    return SimpleNamespace(id=point_id, payload=payload, vector=vector)


class _StubQdrantClient:
    def __init__(
        self, pages: list[tuple[list[SimpleNamespace], int | str | None]], has_colbert=True
    ):
        self._pages = list(pages)
        self.scroll_calls: list[object] = []
        self.update_vectors_calls: list[list] = []
        self.upsert_calls = 0
        vectors: dict[str, object] = {"dense": object()}
        if has_colbert:
            vectors["colbert"] = object()

        self._collection = SimpleNamespace(
            points_count=sum(len(items) for items, _ in pages),
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors=vectors,
                    sparse_vectors={"bm42": object()},
                )
            ),
        )

    def get_collection(self, collection_name: str):
        return self._collection

    def scroll(
        self,
        *,
        collection_name: str,
        limit: int,
        offset=None,
        with_payload=True,
        with_vectors=False,
    ):
        self.scroll_calls.append(offset)
        if self._pages:
            return self._pages.pop(0)
        return [], None

    def update_vectors(self, *, collection_name: str, points: list):
        self.update_vectors_calls.append(points)
        return SimpleNamespace(status="ok")

    def upsert(self, *args, **kwargs):
        self.upsert_calls += 1
        return SimpleNamespace(status="ok")


class _StubBGEClient:
    def __init__(self, responses: list[object]):
        self._responses = list(responses)
        self.calls: list[list[str]] = []

    def encode_colbert(self, texts: list[str]):
        self.calls.append(texts)
        if not self._responses:
            raise RuntimeError("No stub response available")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return SimpleNamespace(colbert_vecs=response)


class TestColbertBackfillRunner:
    def test_backfill_updates_only_missing_colbert_vectors(self, tmp_path: Path):
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        qdrant = _StubQdrantClient(
            pages=[
                (
                    [
                        _record("p1", page_content="already", colbert=[[0.11, 0.22]]),
                        _record("p2", page_content="need backfill"),
                    ],
                    None,
                )
            ]
        )
        bge = _StubBGEClient(responses=[[[[0.3, 0.4]]]])

        runner = ColbertBackfillRunner(
            qdrant_client=qdrant,
            bge_client=bge,
            collection_name="test_col",
            checkpoint_path=tmp_path / "checkpoint.json",
            retry_attempts=2,
            retry_backoff_seconds=0.0,
        )

        stats = runner.run(batch_size=2)

        assert stats.scanned == 2
        assert stats.processed == 1
        assert stats.skipped == 1
        assert stats.failed == 0
        assert len(qdrant.update_vectors_calls) == 1
        assert len(qdrant.update_vectors_calls[0]) == 1
        assert qdrant.update_vectors_calls[0][0].id == "p2"
        assert "colbert" in qdrant.update_vectors_calls[0][0].vector
        assert qdrant.upsert_calls == 0

    def test_backfill_uses_text_fallback_when_page_content_missing(self, tmp_path: Path):
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        qdrant = _StubQdrantClient(pages=[([_record("p1", text="fallback payload text")], None)])
        bge = _StubBGEClient(responses=[[[[0.1, 0.2]]]])
        runner = ColbertBackfillRunner(
            qdrant_client=qdrant,
            bge_client=bge,
            collection_name="test_col",
            checkpoint_path=tmp_path / "checkpoint.json",
            retry_backoff_seconds=0.0,
        )

        stats = runner.run(batch_size=1)
        assert stats.processed == 1
        assert bge.calls == [["fallback payload text"]]

    def test_backfill_dry_run_does_not_write_vectors(self, tmp_path: Path):
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        qdrant = _StubQdrantClient(pages=[([_record("p1", page_content="doc")], None)])
        bge = _StubBGEClient(responses=[[[[0.8, 0.9]]]])
        runner = ColbertBackfillRunner(
            qdrant_client=qdrant,
            bge_client=bge,
            collection_name="test_col",
            checkpoint_path=tmp_path / "checkpoint.json",
            retry_backoff_seconds=0.0,
        )

        stats = runner.run(batch_size=1, dry_run=True)
        assert stats.processed == 1
        assert bge.calls == []
        assert qdrant.update_vectors_calls == []

    def test_backfill_resume_reads_checkpoint_offset(self, tmp_path: Path):
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        checkpoint = tmp_path / "checkpoint.json"
        checkpoint.write_text(json.dumps({"next_offset": 777}), encoding="utf-8")

        qdrant = _StubQdrantClient(pages=[([], None)])
        bge = _StubBGEClient(responses=[])
        runner = ColbertBackfillRunner(
            qdrant_client=qdrant,
            bge_client=bge,
            collection_name="test_col",
            checkpoint_path=checkpoint,
            retry_backoff_seconds=0.0,
        )

        runner.run(batch_size=10, resume=True)
        assert qdrant.scroll_calls[0] == 777

    def test_backfill_retries_bge_and_qdrant_transient_errors(self, tmp_path: Path):
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        qdrant = _StubQdrantClient(pages=[([_record("p1", page_content="doc")], None)])
        qdrant_fail_once = {"calls": 0}
        original_update_vectors = qdrant.update_vectors

        def _flaky_update_vectors(*, collection_name: str, points: list):
            qdrant_fail_once["calls"] += 1
            if qdrant_fail_once["calls"] == 1:
                raise RuntimeError("temporary qdrant error")
            return original_update_vectors(collection_name=collection_name, points=points)

        qdrant.update_vectors = _flaky_update_vectors

        bge = _StubBGEClient(
            responses=[
                RuntimeError("temporary bge timeout"),
                [[[0.3, 0.4]]],
            ]
        )
        runner = ColbertBackfillRunner(
            qdrant_client=qdrant,
            bge_client=bge,
            collection_name="test_col",
            checkpoint_path=tmp_path / "checkpoint.json",
            retry_attempts=3,
            retry_backoff_seconds=0.0,
        )

        stats = runner.run(batch_size=1)
        assert stats.processed == 1
        assert len(bge.calls) == 2
        assert qdrant_fail_once["calls"] == 2

    def test_backfill_respects_retry_attempts_setting(self, tmp_path: Path):
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        qdrant = _StubQdrantClient(pages=[([_record("p1", page_content="doc")], None)])
        bge = _StubBGEClient(
            responses=[
                RuntimeError("temporary bge timeout"),
            ]
        )
        runner = ColbertBackfillRunner(
            qdrant_client=qdrant,
            bge_client=bge,
            collection_name="test_col",
            checkpoint_path=tmp_path / "checkpoint.json",
            retry_attempts=1,
            retry_backoff_seconds=0.0,
        )

        stats = runner.run(batch_size=1)
        assert stats.processed == 0
        assert stats.failed == 1
        assert len(bge.calls) == 1
        assert "batch update failed" in stats.errors[0]

    def test_failed_page_pins_checkpoint_and_resume_retries_it(self, tmp_path: Path):
        """Two-run regression (#599): a failed page must be retried on --resume.

        Run 1: the only page fails after retries are exhausted; the checkpoint
        must stay at the failed page (not advance past it) and must not be
        cleared. Run 2 with --resume retries that page and only clears the
        checkpoint once the work is complete.
        """
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        checkpoint = tmp_path / "checkpoint.json"
        checkpoint.write_text(json.dumps({"next_offset": 0}), encoding="utf-8")

        page = (
            [
                _record("p1", page_content="doc one"),
                _record("p2", page_content="doc two"),
            ],
            None,
        )

        qdrant_1 = _StubQdrantClient(pages=[page])
        bge_1 = _StubBGEClient(responses=[RuntimeError("bge down")])
        runner_1 = ColbertBackfillRunner(
            qdrant_client=qdrant_1,
            bge_client=bge_1,
            collection_name="test_col",
            checkpoint_path=checkpoint,
            retry_attempts=1,
            retry_backoff_seconds=0.0,
        )
        stats_1 = runner_1.run(batch_size=2)
        runner_1.close()

        assert stats_1.failed == 2
        assert stats_1.processed == 0
        assert checkpoint.exists()
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        assert saved["next_offset"] == 0

        qdrant_2 = _StubQdrantClient(pages=[page])
        bge_2 = _StubBGEClient(responses=[[[[0.1, 0.2]], [[0.5, 0.6]]]])
        runner_2 = ColbertBackfillRunner(
            qdrant_client=qdrant_2,
            bge_client=bge_2,
            collection_name="test_col",
            checkpoint_path=checkpoint,
            retry_attempts=1,
            retry_backoff_seconds=0.0,
        )
        stats_2 = runner_2.run(batch_size=2, resume=True)
        runner_2.close()

        assert qdrant_2.scroll_calls[0] == 0
        assert bge_2.calls == [["doc one", "doc two"]]
        assert stats_2.failed == 0
        assert stats_2.processed == 2
        assert not checkpoint.exists()

    def test_resume_after_failed_page_does_not_skip_failed_points(self, tmp_path: Path):
        """Two-run regression (#599): resume must retry p1, not scroll past it."""
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        checkpoint = tmp_path / "checkpoint.json"

        qdrant_1 = _StubQdrantClient(pages=[([_record("p1", page_content="doc one")], 2)])
        bge_1 = _StubBGEClient(responses=[RuntimeError("bge down")])
        runner_1 = ColbertBackfillRunner(
            qdrant_client=qdrant_1,
            bge_client=bge_1,
            collection_name="test_col",
            checkpoint_path=checkpoint,
            retry_attempts=1,
            retry_backoff_seconds=0.0,
        )
        stats_1 = runner_1.run(batch_size=1, limit=1)
        runner_1.close()

        assert stats_1.failed == 1
        assert stats_1.processed == 0
        assert not checkpoint.exists()

        qdrant_2 = _StubQdrantClient(
            pages=[
                ([_record("p1", page_content="doc one")], 2),
                ([_record("p2", page_content="doc two")], None),
            ]
        )
        bge_2 = _StubBGEClient(responses=[[[[0.1, 0.2]]], [[[0.3, 0.4]]]])
        runner_2 = ColbertBackfillRunner(
            qdrant_client=qdrant_2,
            bge_client=bge_2,
            collection_name="test_col",
            checkpoint_path=checkpoint,
            retry_attempts=1,
            retry_backoff_seconds=0.0,
        )
        stats_2 = runner_2.run(batch_size=1, resume=True)
        runner_2.close()

        assert qdrant_2.scroll_calls[0] is None
        assert qdrant_2.scroll_calls[1] == 2
        assert bge_2.calls == [["doc one"], ["doc two"]]
        assert stats_2.processed == 2
        assert stats_2.failed == 0
        assert not checkpoint.exists()

    def test_missing_text_failure_pins_checkpoint_at_failed_page(self, tmp_path: Path):
        """A point without text fails the page: the checkpoint stays at its start."""
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        checkpoint = tmp_path / "checkpoint.json"
        checkpoint.write_text(json.dumps({"next_offset": 0}), encoding="utf-8")

        qdrant = _StubQdrantClient(
            pages=[([_record("p1"), _record("p2", page_content="doc two")], None)]
        )
        bge = _StubBGEClient(responses=[[[[0.3, 0.4]]]])
        runner = ColbertBackfillRunner(
            qdrant_client=qdrant,
            bge_client=bge,
            collection_name="test_col",
            checkpoint_path=checkpoint,
            retry_attempts=1,
            retry_backoff_seconds=0.0,
        )
        stats = runner.run(batch_size=2)
        runner.close()

        assert stats.failed == 1
        assert stats.processed == 1
        assert qdrant.update_vectors_calls[0][0].id == "p2"
        assert checkpoint.exists()
        saved = json.loads(checkpoint.read_text(encoding="utf-8"))
        assert saved["next_offset"] == 0

    def test_backfill_fails_fast_when_colbert_schema_missing(self, tmp_path: Path):
        from src.ingestion.unified.colbert_backfill import ColbertBackfillRunner

        qdrant = _StubQdrantClient(pages=[([], None)], has_colbert=False)
        bge = _StubBGEClient(responses=[])
        runner = ColbertBackfillRunner(
            qdrant_client=qdrant,
            bge_client=bge,
            collection_name="test_col",
            checkpoint_path=tmp_path / "checkpoint.json",
        )

        with pytest.raises(RuntimeError, match="colbert"):
            runner.run(batch_size=1)


class TestCmdBackfillColbert:
    """Wiring of the backfill-colbert command.

    ``main()`` dispatch behavior (backfill-colbert, schema-check,
    coverage-check) lives in test_unified_cli.py::TestMainDispatch (#3406
    removed the duplicate dispatch block from this file).
    """

    def test_cmd_backfill_colbert_wires_runner(self):
        from src.ingestion.unified.cli import cmd_backfill_colbert

        args = SimpleNamespace(batch_size=64, limit=100, dry_run=True, resume=True)
        fake_runner = MagicMock()
        fake_runner.run.return_value = SimpleNamespace(
            scanned=100,
            processed=80,
            skipped=20,
            failed=0,
        )

        with patch(
            "src.ingestion.unified.commands.ColbertBackfillRunner", return_value=fake_runner
        ):
            result = cmd_backfill_colbert(args)

        assert result == 0
        fake_runner.run.assert_called_once_with(
            batch_size=64,
            limit=100,
            dry_run=True,
            resume=True,
        )
