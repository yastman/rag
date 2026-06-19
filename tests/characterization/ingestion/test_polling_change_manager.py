"""Characterization tests for FilePollingChangeManager and run_watch (issue #2833).

Covers delete-sweep and watch-mode parity without CocoIndex:
  1. FilePollingChangeManager.detect_changes emits 'deleted' for missing files
  2. FilePollingChangeManager.detect_changes emits 'added' for new files
  3. FilePollingChangeManager.detect_changes emits 'modified' for changed hash
  4. FilePollingChangeManager.record_state delegates to state_manager.upsert_state
  5. UnifiedIngestionOrchestrator.run_watch calls run_once in a loop
  6. run_watch stops when stop_event is set
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.ingestion.unified.orchestrator import (
    FilePollingChangeManager,
    UnifiedIngestionOrchestrator,
)


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state_row(file_id: str, source_path: str, content_hash: str, status: str = "indexed") -> Any:
    row = MagicMock()
    row.file_id = file_id
    row.source_path = source_path
    row.content_hash = content_hash
    row.status = status
    return row


# ---------------------------------------------------------------------------
# 1. detect_changes: deleted files
# ---------------------------------------------------------------------------


class TestDetectChangesDeleted:
    @pytest.mark.asyncio
    async def test_deleted_file_emitted_when_not_on_disk(self, tmp_path: Path) -> None:
        """A file indexed in state but absent from disk → 'deleted' change."""
        state_manager = MagicMock()
        # One indexed file that no longer exists on disk
        state_manager.get_all_indexed_file_ids = AsyncMock(return_value={"fid1"})
        state_manager.get_state = AsyncMock(
            return_value=_state_row("fid1", str(tmp_path / "gone.md"), "hash1")
        )

        manager = FilePollingChangeManager(
            sync_dir=tmp_path,
            state_manager=state_manager,
        )
        changes = await manager.detect_changes("test_col")

        deleted = [c for c in changes if c.kind == "deleted"]
        assert len(deleted) == 1
        assert deleted[0].file_path == str(tmp_path / "gone.md")

    @pytest.mark.asyncio
    async def test_no_deleted_when_file_still_on_disk(self, tmp_path: Path) -> None:
        """A file that still exists on disk → no 'deleted' change."""
        existing = tmp_path / "present.md"
        existing.write_text("hello")

        state_manager = MagicMock()
        state_manager.get_all_indexed_file_ids = AsyncMock(return_value={"fid1"})
        state_manager.get_state = AsyncMock(
            return_value=_state_row("fid1", str(existing), "hash_old")
        )

        manager = FilePollingChangeManager(sync_dir=tmp_path, state_manager=state_manager)
        changes = await manager.detect_changes("test_col")

        deleted = [c for c in changes if c.kind == "deleted"]
        assert len(deleted) == 0


# ---------------------------------------------------------------------------
# 2. detect_changes: added files
# ---------------------------------------------------------------------------


class TestDetectChangesAdded:
    @pytest.mark.asyncio
    async def test_new_file_on_disk_emitted_as_added(self, tmp_path: Path) -> None:
        """A file on disk with no state entry → 'added' change."""
        new_file = tmp_path / "new.md"
        new_file.write_text("content")

        state_manager = MagicMock()
        state_manager.get_all_indexed_file_ids = AsyncMock(return_value=set())
        state_manager.get_state = AsyncMock(return_value=None)

        manager = FilePollingChangeManager(sync_dir=tmp_path, state_manager=state_manager)
        changes = await manager.detect_changes("test_col")

        added = [c for c in changes if c.kind == "added"]
        assert any(c.file_path == str(new_file) for c in added)


# ---------------------------------------------------------------------------
# 3. detect_changes: modified files
# ---------------------------------------------------------------------------


class TestDetectChangesModified:
    @pytest.mark.asyncio
    async def test_changed_content_emitted_as_modified(self, tmp_path: Path) -> None:
        """A file with different hash from stored state → 'modified' change."""
        changed = tmp_path / "changed.md"
        changed.write_bytes(b"new content")

        import hashlib

        new_hash = hashlib.sha256(b"new content").hexdigest()[:16]
        old_hash = "deadbeef00000000"
        assert new_hash != old_hash

        state_manager = MagicMock()
        state_manager.get_all_indexed_file_ids = AsyncMock(return_value={"fid1"})
        state_manager.get_state = AsyncMock(return_value=_state_row("fid1", str(changed), old_hash))

        manager = FilePollingChangeManager(sync_dir=tmp_path, state_manager=state_manager)
        changes = await manager.detect_changes("test_col")

        modified = [c for c in changes if c.kind == "modified"]
        assert any(c.file_path == str(changed) for c in modified)


# ---------------------------------------------------------------------------
# 4. record_state: delegates to state_manager.upsert_state
# ---------------------------------------------------------------------------


class TestRecordState:
    @pytest.mark.asyncio
    async def test_record_state_calls_upsert_state(self, tmp_path: Path) -> None:
        state_manager = MagicMock()
        state_manager.upsert_state = AsyncMock()
        state_manager.get_all_indexed_file_ids = AsyncMock(return_value=set())

        file_state = MagicMock()

        manager = FilePollingChangeManager(sync_dir=tmp_path, state_manager=state_manager)
        await manager.record_state("docs/a.md", "test_col", file_state)

        state_manager.upsert_state.assert_called_once_with(file_state)


# ---------------------------------------------------------------------------
# 5 & 6. run_watch: polling loop with stop_event
# ---------------------------------------------------------------------------


class TestRunWatch:
    @pytest.mark.asyncio
    async def test_run_watch_calls_run_once_until_stop(self) -> None:
        """run_watch loops, calling run_once, until stop_event is set."""
        stop_event = asyncio.Event()
        call_count = 0

        async def fake_run_once(collection_name: str):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                stop_event.set()
            from src.ingestion.unified.orchestrator import IngestionResult

            return IngestionResult(processed=1)

        change_manager = MagicMock()
        writer = MagicMock()
        state_manager = MagicMock()

        orch = UnifiedIngestionOrchestrator(
            change_manager=change_manager,
            writer=writer,
            state_manager=state_manager,
        )
        orch.run_once = fake_run_once  # type: ignore[method-assign]

        await orch.run_watch("test_col", stop_event=stop_event, poll_interval=0.01)

        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_run_watch_stops_immediately_when_event_preset(self) -> None:
        """If stop_event is already set, run_watch exits without calling run_once."""
        stop_event = asyncio.Event()
        stop_event.set()

        run_once_called = False

        async def fake_run_once(collection_name: str):
            nonlocal run_once_called
            run_once_called = True
            from src.ingestion.unified.orchestrator import IngestionResult

            return IngestionResult()

        change_manager = MagicMock()
        writer = MagicMock()
        state_manager = MagicMock()

        orch = UnifiedIngestionOrchestrator(
            change_manager=change_manager,
            writer=writer,
            state_manager=state_manager,
        )
        orch.run_once = fake_run_once  # type: ignore[method-assign]

        await orch.run_watch("test_col", stop_event=stop_event, poll_interval=0.01)

        assert not run_once_called
