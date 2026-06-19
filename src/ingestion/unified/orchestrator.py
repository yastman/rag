# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
"""Flag-gated UnifiedIngestionOrchestrator.

Decouples the ingestion loop from CocoIndex via FileChangeManager and
DocumentWriter protocols. See docs/designs/epic-2836-ingest-decouple.md.

Enable with: INGEST_USE_NEW_ORCHESTRATOR=true
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
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

    async def run_watch(self, collection_name: str) -> None:
        """Run ingestion continuously (delegates to change_manager for loop control)."""
        raise NotImplementedError("run_watch is change-manager-specific; implement in subclass")
