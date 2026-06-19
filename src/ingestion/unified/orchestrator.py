# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
"""Flag-gated UnifiedIngestionOrchestrator.

Decouples the ingestion loop from CocoIndex via FileChangeManager and
DocumentWriter protocols. See docs/designs/epic-2836-ingest-decouple.md.

Enable with: INGEST_USE_NEW_ORCHESTRATOR=true
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Protocol


if TYPE_CHECKING:
    from src.ingestion.unified.state_manager import FileState, UnifiedStateManager


logger = logging.getLogger(__name__)


def is_new_orchestrator_enabled() -> bool:
    """Return True when INGEST_USE_NEW_ORCHESTRATOR is set to a truthy value."""
    val = os.environ.get("INGEST_USE_NEW_ORCHESTRATOR", "").strip().lower()
    return val in ("1", "true", "yes")


@dataclass
class FileChange:
    """Represents a detected file change."""

    file_path: str
    kind: str  # "added" | "modified" | "deleted"


@dataclass
class IngestionResult:
    """Summary of a run_once pass."""

    processed: int = 0
    deleted: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)


class FileChangeManager(Protocol):
    """Detects file changes and records processing state."""

    async def detect_changes(self, collection_name: str) -> list[FileChange]: ...

    async def record_state(
        self,
        file_path: str,
        collection_name: str,
        state: FileState,
    ) -> None: ...


class DocumentWriter(Protocol):
    """Writes/deletes documents in the vector store."""

    async def write_file(self, file_path: str, collection_name: str) -> FileState: ...

    async def delete_file(self, file_path: str, collection_name: str) -> None: ...


class UnifiedIngestionOrchestrator:
    """Ingestion loop decoupled from CocoIndex.

    Accepts injected FileChangeManager and DocumentWriter so the
    change-detection backend can be swapped without touching this loop.
    """

    def __init__(
        self,
        change_manager: FileChangeManager,
        writer: DocumentWriter,
        state_manager: UnifiedStateManager,
    ) -> None:
        self.change_manager = change_manager
        self.writer = writer
        self.state_manager = state_manager

    async def run_once(self, collection_name: str) -> IngestionResult:
        """Detect changes, process files, update state."""
        result = IngestionResult()
        changes = await self.change_manager.detect_changes(collection_name)

        for change in changes:
            try:
                if change.kind in ("added", "modified"):
                    state = await self.writer.write_file(change.file_path, collection_name)
                    await self.change_manager.record_state(change.file_path, collection_name, state)
                    result.processed += 1
                elif change.kind == "deleted":
                    await self.writer.delete_file(change.file_path, collection_name)
                    result.deleted += 1
                else:
                    logger.warning("Unknown change kind %r for %s", change.kind, change.file_path)
            except Exception as exc:
                logger.error("Error processing %s: %s", change.file_path, exc, exc_info=True)
                result.errors += 1
                result.error_details.append(f"{change.file_path}: {exc}")

        return result

    async def run_watch(
        self,
        collection_name: str,
        stop_event: asyncio.Event | None = None,
        poll_interval: float = 30.0,
    ) -> None:
        """Run ingestion in a polling loop until stop_event is set.

        Args:
            collection_name: Qdrant collection to ingest into.
            stop_event: When set, the loop exits after the current pass.
                If already set on entry, exits immediately without running.
            poll_interval: Seconds to wait between passes.
        """
        if stop_event is None:
            stop_event = asyncio.Event()

        while not stop_event.is_set():
            result = await self.run_once(collection_name)
            logger.info(
                "run_watch pass: processed=%d deleted=%d errors=%d",
                result.processed,
                result.deleted,
                result.errors,
            )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval)


# ---------------------------------------------------------------------------
# FilePollingChangeManager — filesystem-based FileChangeManager
# ---------------------------------------------------------------------------

#: File extensions scanned by the polling manager (mirrors flow.py patterns).
_POLLING_EXTENSIONS: frozenset[str] = frozenset(
    {".pdf", ".docx", ".doc", ".xlsx", ".pptx", ".md", ".txt", ".html", ".htm", ".csv"}
)


def _compute_file_hash(path: Path) -> str:
    """Return a 16-char sha256 hex digest of the file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


class FilePollingChangeManager:
    """FileChangeManager that polls the filesystem for changes.

    Compares on-disk files against Postgres ingestion state to detect
    added, modified, and deleted files. Does not require CocoIndex.

    Delete-sweep: any file_id in state with status='indexed' whose
    source_path no longer exists on disk is emitted as 'deleted'.
    """

    def __init__(
        self,
        sync_dir: Path,
        state_manager: UnifiedStateManager,
    ) -> None:
        self.sync_dir = sync_dir
        self.state_manager = state_manager

    async def detect_changes(self, collection_name: str) -> list[FileChange]:
        changes: list[FileChange] = []

        # --- Delete sweep: indexed files whose source_path is missing ---
        indexed_ids = await self.state_manager.get_all_indexed_file_ids()
        indexed_paths: dict[str, str] = {}  # source_path → content_hash

        for file_id in indexed_ids:
            state = await self.state_manager.get_state(file_id)
            if state is None or not state.source_path:
                continue
            if not Path(state.source_path).exists():
                changes.append(FileChange(file_path=state.source_path, kind="deleted"))
            elif state.content_hash:
                indexed_paths[state.source_path] = state.content_hash

        # --- Scan disk for added / modified ---
        for path in self.sync_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in _POLLING_EXTENSIONS:
                continue
            path_str = str(path)
            if path_str in indexed_paths:
                current_hash = _compute_file_hash(path)
                if current_hash != indexed_paths[path_str]:
                    changes.append(FileChange(file_path=path_str, kind="modified"))
            else:
                changes.append(FileChange(file_path=path_str, kind="added"))

        return changes

    async def record_state(
        self,
        file_path: str,
        collection_name: str,
        state: FileState,
    ) -> None:
        """Persist file state after successful write."""
        await self.state_manager.upsert_state(state)
