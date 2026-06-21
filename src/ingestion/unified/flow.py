# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
"""Pure-Python ingestion flow helpers.

CocoIndex has been removed (#2834). Ingestion runs via UnifiedIngestionOrchestrator
with FilePollingChangeManager and QdrantHybridTargetConnector.

This module retains the pure utility helpers (MIME detection, manifest-based
file-ID) so callers that imported them directly keep working.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.ingestion.unified.manifest import FileManifest, compute_content_hash_from_bytes
from src.ingestion.unified.observability import observe, try_update_ingestion_trace


if TYPE_CHECKING:
    from src.ingestion.unified.config import UnifiedConfig
    from src.ingestion.unified.orchestrator import UnifiedIngestionOrchestrator
    from src.ingestion.unified.state_manager import FileState


logger = logging.getLogger(__name__)


MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".html": "text/html",
    ".htm": "text/html",
    ".csv": "text/csv",
}


def get_mime_type(relative_path: str) -> str:
    """Get MIME type from file extension."""
    ext = Path(relative_path).suffix.lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


# Global manifest instance, initialised by callers that need manifest-based IDs.
_manifest: FileManifest | None = None

# Global to store sync_dir for abs_path computation.
_current_sync_dir: str = ""


def file_id_from_content(filename: str, content: bytes | None) -> str:
    """Manifest-based file_id: content hash → stable UUID.

    If a file is renamed/moved but content is unchanged, the same
    file_id is returned, preventing duplicates in Qdrant.
    """
    if _manifest is None or content is None:
        return hashlib.sha256(filename.encode()).hexdigest()[:16]
    content_hash = compute_content_hash_from_bytes(content)
    return _manifest.get_or_create_id(filename, content_hash)


def mime_type_from_filename(filename: str) -> str:
    return get_mime_type(filename)


def file_size_from_bytes(content: bytes | None) -> int:
    return len(content) if content is not None else 0


def basename_from_filename(filename: str) -> str:
    return Path(filename).name


def abs_path_from_filename(filename: str) -> str:
    """Compute absolute path from relative filename and sync_dir."""
    return str(Path(_current_sync_dir) / filename)


def _flow_name_for(config: UnifiedConfig) -> str:
    # Keep short for naming compatibility with any stored flow references.
    suffix = hashlib.sha256(config.collection_name.encode()).hexdigest()[:6]
    return f"ingest_{suffix}"


def _app_namespace_for(config: UnifiedConfig) -> str:
    return "unified"


def _build_orchestrator(config: UnifiedConfig) -> UnifiedIngestionOrchestrator:
    """Construct a wired UnifiedIngestionOrchestrator from config."""
    from src.ingestion.unified.orchestrator import (
        FilePollingChangeManager,
        UnifiedIngestionOrchestrator,
    )
    from src.ingestion.unified.state_manager import UnifiedStateManager
    from src.ingestion.unified.targets.qdrant_hybrid_target import (
        QdrantHybridTargetConnector,
        QdrantHybridTargetSpec,
        QdrantHybridTargetValues,
    )

    spec = QdrantHybridTargetSpec.from_config(config)
    state_manager = UnifiedStateManager(database_url=config.database_url)

    class _TargetDocumentWriter:
        """DocumentWriter bridge to QdrantHybridTargetConnector (sync → async)."""

        async def write_file(self, file_path: str, collection_name: str) -> FileState:
            from src.ingestion.unified.flow import (
                file_id_from_content,
                get_mime_type,
            )
            from src.ingestion.unified.state_manager import FileState as _FileState

            path = Path(file_path)
            content = path.read_bytes() if path.exists() else None
            file_id = file_id_from_content(str(path.name), content)
            values = QdrantHybridTargetValues(
                abs_path=file_path,
                source_path=file_path,
                file_name=path.name,
                mime_type=get_mime_type(file_path),
                file_size=len(content) if content is not None else 0,
            )
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: QdrantHybridTargetConnector.mutate((spec, {file_id: values})),
            )
            return _FileState(file_id=file_id, source_path=file_path, status="indexed")

        async def delete_file(self, file_path: str, collection_name: str) -> None:
            from src.ingestion.unified.flow import file_id_from_content

            path = Path(file_path)
            file_id = file_id_from_content(str(path.name), None)
            # ponytail: mutate() treats None value as delete; type stub is too narrow
            mutations: dict[str, QdrantHybridTargetValues] = {file_id: None}  # type: ignore[dict-item]
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: QdrantHybridTargetConnector.mutate((spec, mutations)),
            )

    change_manager = FilePollingChangeManager(
        sync_dir=config.sync_dir,
        state_manager=state_manager,
    )
    return UnifiedIngestionOrchestrator(
        change_manager=change_manager,
        writer=_TargetDocumentWriter(),
        state_manager=state_manager,
    )


@observe(name="ingestion-flow-run-once", capture_input=False, capture_output=False)
def run_once(config: UnifiedConfig | None = None) -> None:
    """Run ingestion once (single pass) via UnifiedIngestionOrchestrator."""
    from src.ingestion.unified.config import UnifiedConfig as _Cfg

    if config is None:
        config = _Cfg()
    try_update_ingestion_trace(command="flow-run-once", status="started")
    try:
        orchestrator = _build_orchestrator(config)
        asyncio.run(orchestrator.run_once(config.collection_name))
    except Exception as exc:
        try_update_ingestion_trace(
            command="flow-run-once",
            status="error",
            metadata={"error_type": type(exc).__name__},
        )
        raise
    try_update_ingestion_trace(command="flow-run-once", status="completed")


@observe(name="ingestion-flow-watch", capture_input=False, capture_output=False)
def run_watch(
    config: UnifiedConfig | None = None,
    stop_event: asyncio.Event | None = None,
) -> None:
    """Run ingestion continuously via UnifiedIngestionOrchestrator."""
    from src.ingestion.unified.config import UnifiedConfig as _Cfg

    if config is None:
        config = _Cfg()
    try_update_ingestion_trace(command="flow-watch", status="started")
    try:
        orchestrator = _build_orchestrator(config)
        asyncio.run(orchestrator.run_watch(config.collection_name, stop_event=stop_event))
    except Exception as exc:
        try_update_ingestion_trace(
            command="flow-watch",
            status="error",
            metadata={"error_type": type(exc).__name__},
        )
        raise
    try_update_ingestion_trace(command="flow-watch", status="completed")
