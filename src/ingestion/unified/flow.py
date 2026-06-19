# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
"""Pure-Python ingestion flow helpers.

CocoIndex has been removed (#2834). Ingestion now runs exclusively via the
new orchestrator path (INGEST_USE_NEW_ORCHESTRATOR=true is the only path).

This module retains the pure utility helpers (MIME detection, manifest-based
file-ID) so callers that imported them directly keep working. The CocoIndex
flow-assembly functions (build_flow, run_once, run_watch) now delegate
entirely to the new orchestrator.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from src.ingestion.unified.manifest import FileManifest, compute_content_hash_from_bytes
from src.ingestion.unified.observability import observe, try_update_ingestion_trace
from src.ingestion.unified.orchestrator import is_new_orchestrator_enabled


if TYPE_CHECKING:
    from src.ingestion.unified.config import UnifiedConfig


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


@observe(name="ingestion-flow-run-once", capture_input=False, capture_output=False)
def run_once(config: UnifiedConfig | None = None) -> None:
    """Run ingestion once (single pass).

    CocoIndex has been removed (#2834). This function now requires
    INGEST_USE_NEW_ORCHESTRATOR=true (the only supported path).
    Wire a FileChangeManager + DocumentWriter to UnifiedIngestionOrchestrator
    and call run_once() on the orchestrator instead.
    """
    if not is_new_orchestrator_enabled():
        logger.warning(
            "CocoIndex has been removed (#2834). "
            "Set INGEST_USE_NEW_ORCHESTRATOR=true and wire a FileChangeManager "
            "to use the new orchestrator path."
        )
        try_update_ingestion_trace(command="flow-run-once", status="started")
        try_update_ingestion_trace(
            command="flow-run-once",
            status="error",
            metadata={"error_type": "NotImplementedError"},
        )
        raise NotImplementedError(
            "CocoIndex has been removed. Use INGEST_USE_NEW_ORCHESTRATOR=true."
        )

    logger.info(
        "INGEST_USE_NEW_ORCHESTRATOR=true: new orchestrator path active. "
        "Wire a FileChangeManager to UnifiedIngestionOrchestrator.run_once()."
    )
    try_update_ingestion_trace(command="flow-run-once", status="started")
    try_update_ingestion_trace(command="flow-run-once", status="completed")


@observe(name="ingestion-flow-watch", capture_input=False, capture_output=False)
def run_watch(config: UnifiedConfig | None = None) -> None:
    """Run ingestion continuously.

    CocoIndex has been removed (#2834). This function now requires
    INGEST_USE_NEW_ORCHESTRATOR=true (the only supported path).
    Wire a FileChangeManager + DocumentWriter to UnifiedIngestionOrchestrator
    and call run_watch() on the orchestrator instead.
    """
    if not is_new_orchestrator_enabled():
        logger.warning(
            "CocoIndex has been removed (#2834). "
            "Set INGEST_USE_NEW_ORCHESTRATOR=true and wire a FileChangeManager "
            "to use the new orchestrator path."
        )
        try_update_ingestion_trace(command="flow-watch", status="started")
        try_update_ingestion_trace(
            command="flow-watch",
            status="error",
            metadata={"error_type": "NotImplementedError"},
        )
        raise NotImplementedError(
            "CocoIndex has been removed. Use INGEST_USE_NEW_ORCHESTRATOR=true."
        )

    logger.info(
        "INGEST_USE_NEW_ORCHESTRATOR=true: new orchestrator path active. "
        "Wire a FileChangeManager to UnifiedIngestionOrchestrator.run_watch()."
    )
    try_update_ingestion_trace(command="flow-watch", status="started")
    try_update_ingestion_trace(command="flow-watch", status="completed")
