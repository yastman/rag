# SPDX-License-Identifier: MIT
# Copyright (c) 2025 RAG-Fresh contributors.
"""Stateless unified ingestion flow.

Scan ``sync_dir`` → parse Markdown → embed via BGE-M3 → upsert into Qdrant.

Production ingestion is Markdown-only (#3235): exactly ``.md`` files are
accepted, parsed by the stdlib :class:`~src.ingestion.markdown.MarkdownParser`.

Idempotency lives entirely in Qdrant: every point carries
``metadata.content_hash`` (written by :class:`QdrantHybridWriter`). Before
parsing a file we scroll for a point with this file's ``(file_id,
content_hash)`` — if one exists the file is unchanged and skipped without
re-parsing/re-embedding. There is no external state database (the Postgres
``UnifiedStateManager``/``UnifiedIngestionOrchestrator`` were removed).

``QdrantHybridWriter.upsert_chunks_sync`` already replaces a file's points
atomically (deterministic ids overwrite in place, stale chunk ids are swept
afterwards), so a *changed* file is re-ingested correctly.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING

from qdrant_client.models import FieldCondition, Filter, MatchValue

from src.ingestion.unified.manifest import FileManifest, compute_content_hash_from_bytes
from src.ingestion.unified.observability import try_update_ingestion_trace
from src.ingestion.unified.qdrant_writer import QdrantHybridWriter


if TYPE_CHECKING:
    from src.ingestion.markdown import MarkdownParser
    from src.ingestion.unified.config import UnifiedConfig


logger = logging.getLogger(__name__)


MIME_TYPES = {
    ".md": "text/markdown",
}


def get_mime_type(relative_path: str) -> str:
    """Get MIME type from file extension."""
    ext = Path(relative_path).suffix.lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


# Global manifest instance, initialised by run_once before scanning so that
# file_id_from_content() can resolve stable, rename-aware ids.
_manifest: FileManifest | None = None


_source_locks: dict[str, Lock] = {}
_source_locks_guard = Lock()


def _lock_for_source(source_path: str) -> Lock:
    """Return the process-local lock for replacements of one stable source."""
    with _source_locks_guard:
        return _source_locks.setdefault(source_path, Lock())


def _file_ids_for_source(client: object, collection_name: str, source_path: str) -> set[str]:
    """Return every file id currently stored for one stable source path."""
    source_filter = Filter(
        must=[FieldCondition(key="metadata.source", match=MatchValue(value=source_path))]
    )
    file_ids: set[str] = set()
    offset = None
    while True:
        records, offset = client.scroll(  # type: ignore[attr-defined]
            collection_name=collection_name,
            scroll_filter=source_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for record in records:
            payload = getattr(record, "payload", None)
            if payload is None and isinstance(record, dict):
                payload = record.get("payload")
            metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
            if file_id := metadata.get("file_id"):
                file_ids.add(str(file_id))
        if offset is None:
            return file_ids


def file_id_from_content(filename: str, content: bytes | None) -> str:
    """Manifest-based file_id: content hash → stable UUID.

    If a file is renamed/moved but content is unchanged, the same file_id is
    returned, preventing duplicates in Qdrant. Falls back to a path hash when
    no manifest is loaded or content is unavailable.
    """
    if _manifest is None or content is None:
        return hashlib.sha256(filename.encode()).hexdigest()[:16]
    content_hash = compute_content_hash_from_bytes(content)
    return _manifest.get_or_create_id(filename, content_hash)


@dataclass
class IngestionResult:
    """Summary of a single ``run_once`` pass."""

    processed: int = 0
    skipped: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)


def _make_parser(config: UnifiedConfig) -> MarkdownParser:
    """Construct the Markdown parser with the configured chunk budget."""
    from src.ingestion.markdown import MarkdownParser

    return MarkdownParser(max_tokens=config.max_tokens_per_chunk)


def _already_indexed(client: object, collection_name: str, file_id: str, content_hash: str) -> bool:
    """Return True if Qdrant already holds a point for this (file_id, hash).

    ponytail: any scroll failure (missing collection, transient error) is
    treated as "not indexed" so the file is re-ingested. That is safe because
    upsert uses deterministic point ids (re-ingest is idempotent), at the cost
    of redundant work when Qdrant is briefly unreachable.
    """
    try:
        records, _ = client.scroll(  # type: ignore[attr-defined]
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(key="metadata.file_id", match=MatchValue(value=file_id)),
                    FieldCondition(
                        key="metadata.content_hash", match=MatchValue(value=content_hash)
                    ),
                ]
            ),
            limit=1,
            with_payload=False,
            with_vectors=False,
        )
    except Exception as exc:  # ponytail: any scroll failure → re-ingest (idempotent)
        logger.debug("Dedup scroll failed for %s (%s); will re-ingest", file_id, exc)
        return False
    return bool(records)


def _ingest_directory(
    config: UnifiedConfig,
    writer: QdrantHybridWriter,
    parser: MarkdownParser,
) -> IngestionResult:
    """Scan sync_dir once and upsert every new/changed supported file."""
    result = IngestionResult()
    collection = config.collection_name

    for path in sorted(config.sync_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in config.supported_extensions:
            continue

        rel = str(path.relative_to(config.sync_dir))
        try:
            content = path.read_bytes()
            content_hash = compute_content_hash_from_bytes(content)
            file_id = file_id_from_content(rel, content)

            if _already_indexed(writer.client, collection, file_id, content_hash):
                logger.debug("Skipping unchanged: %s", rel)
                result.skipped += 1
                continue

            parsed_chunks = parser.chunk_file_sync(path)
            if not parsed_chunks:
                logger.warning("No chunks from: %s", rel)
                result.skipped += 1
                continue

            chunks = parser.to_ingestion_chunks(
                parsed_chunks,
                source=rel,
                source_type=path.suffix.lstrip("."),
            )
            file_metadata = {
                "file_name": path.name,
                "mime_type": get_mime_type(rel),
                "file_size": len(content),
                "content_hash": content_hash,
                "modified_time": datetime.now(UTC).isoformat(),
            }

            # A changed manifest entry gets a new file id. Snapshot and replace
            # under the stable-source lock so a failed replacement preserves the
            # old searchable points and concurrent replacements cannot sweep each
            # other's new ids.
            with _lock_for_source(rel):
                old_file_ids = _file_ids_for_source(writer.client, collection, rel)
                stats = writer.upsert_chunks_sync(
                    chunks=chunks,
                    file_id=file_id,
                    source_path=rel,
                    file_metadata=file_metadata,
                    collection_name=collection,
                )
                if stats.errors:
                    raise RuntimeError("; ".join(stats.errors))
                for old_file_id in old_file_ids - {file_id}:
                    writer.delete_file_sync(file_id=old_file_id, collection_name=collection)

            result.processed += 1
            logger.info("Indexed %s (%d chunks)", rel, stats.points_upserted)
        except Exception as exc:  # one bad file must not abort the whole pass
            logger.error("Failed %s: %s", rel, exc, exc_info=True)
            result.errors += 1
            result.error_details.append(f"{rel}: {exc}")

    logger.info(
        "Ingest pass: processed=%d skipped=%d errors=%d",
        result.processed,
        result.skipped,
        result.errors,
    )
    return result


def _build_writer(config: UnifiedConfig) -> QdrantHybridWriter:
    return QdrantHybridWriter(
        qdrant_url=config.qdrant_url,
        qdrant_api_key=config.qdrant_api_key,
        bge_m3_url=config.bge_m3_url,
        bge_m3_timeout=config.bge_m3_timeout,
        bge_m3_concurrency=config.bge_m3_concurrency,
    )


def run_once(config: UnifiedConfig | None = None) -> IngestionResult:
    """Run ingestion once (single pass), stateless and idempotent."""
    from src.ingestion.unified.config import UnifiedConfig as _Cfg

    if config is None:
        config = _Cfg()

    global _manifest
    _manifest = FileManifest(config.effective_manifest_dir())

    try_update_ingestion_trace(command="flow-run-once", status="started")
    try:
        writer = _build_writer(config)
        parser = _make_parser(config)
        result = _ingest_directory(config, writer, parser)
    except Exception as exc:
        try_update_ingestion_trace(
            command="flow-run-once",
            status="error",
            metadata={"error_type": type(exc).__name__},
        )
        raise
    try_update_ingestion_trace(
        command="flow-run-once",
        status="completed",
        metadata={
            "processed": result.processed,
            "skipped": result.skipped,
            "errors": result.errors,
        },
    )
    return result


def run_watch(
    config: UnifiedConfig | None = None,
    stop_event: object | None = None,
) -> None:
    """Run ingestion continuously: a polling loop over ``run_once``.

    ``stop_event`` is any object exposing ``is_set()`` (e.g. ``threading.Event``
    or ``asyncio.Event``); when set after a pass the loop exits. With no event
    the loop runs until interrupted (Ctrl-C). Replaces the old Postgres-backed
    orchestrator watch loop — no stuck-row reaping is needed without state.
    """
    from src.ingestion.unified.config import UnifiedConfig as _Cfg

    if config is None:
        config = _Cfg()

    poll = float(getattr(config, "poll_interval_seconds", 60))
    try_update_ingestion_trace(command="flow-watch", status="started")
    try:
        while True:
            run_once(config)
            if stop_event is not None and stop_event.is_set():  # type: ignore[attr-defined]
                break
            time.sleep(poll)
    except KeyboardInterrupt:
        try_update_ingestion_trace(command="flow-watch", status="interrupted")
        return
    except Exception as exc:
        try_update_ingestion_trace(
            command="flow-watch",
            status="error",
            metadata={"error_type": type(exc).__name__},
        )
        raise
    try_update_ingestion_trace(command="flow-watch", status="completed")
