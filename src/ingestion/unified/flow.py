# src/ingestion/unified/flow.py
"""CocoIndex flow for unified ingestion pipeline.

This module is intentionally minimal:
- CocoIndex handles incremental change detection via `sources.LocalFile`.
- A custom target connector performs docling → embeddings → Qdrant upsert/delete.
"""

import hashlib
import logging
from datetime import timedelta
from pathlib import Path

import cocoindex
from cocoindex import setting
from cocoindex.flow import flow_by_name, flow_names
from cocoindex.op import function as cocoindex_function

from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.targets.qdrant_hybrid_target import (
    QdrantHybridTargetConnector,  # noqa: F401 - registers the connector
    QdrantHybridTargetSpec,
)


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


def compute_file_id(relative_path: str) -> str:
    """Compute stable file_id from relative path."""
    return hashlib.sha256(relative_path.encode()).hexdigest()[:16]


def get_mime_type(relative_path: str) -> str:
    """Get MIME type from file extension."""
    ext = Path(relative_path).suffix.lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


@cocoindex_function()
def file_id_from_filename(filename: str) -> str:
    return compute_file_id(filename)


@cocoindex_function()
def mime_type_from_filename(filename: str) -> str:
    return get_mime_type(filename)


@cocoindex_function()
def file_size_from_bytes(content: bytes | None) -> int:
    return len(content) if content is not None else 0


@cocoindex_function()
def basename_from_filename(filename: str) -> str:
    return Path(filename).name


def _flow_name_for(config: UnifiedConfig) -> str:
    # Keep short to stay under 64 char limit for full flow name.
    # Use hash suffix for uniqueness across collections.
    suffix = hashlib.sha256(config.collection_name.encode()).hexdigest()[:6]
    return f"ingest_{suffix}"


def _app_namespace_for(config: UnifiedConfig) -> str:
    # CocoIndex full name = "{app_namespace}.{flow_name}" must be <= 64 chars.
    # Keep namespace short.
    return "unified"


def build_flow(config: UnifiedConfig | None = None) -> cocoindex.Flow:
    """Build and register the unified CocoIndex flow."""
    if config is None:
        config = UnifiedConfig()

    # Init CocoIndex with explicit database settings (do not rely on env vars).
    cocoindex.init(
        setting.Settings(
            database=setting.DatabaseConnectionSpec(url=config.database_url),
            app_namespace=_app_namespace_for(config),
        )
    )

    flow_name = _flow_name_for(config)
    if flow_name in flow_names():
        flow_by_name(flow_name).close()

    def flow_def(flow_builder: cocoindex.FlowBuilder, data_scope: cocoindex.DataScope) -> None:
        sync_dir = str(config.sync_dir)

        included_patterns = [
            "**/*.pdf",
            "**/*.docx",
            "**/*.doc",
            "**/*.xlsx",
            "**/*.pptx",
            # For dev/e2e
            "**/*.md",
            "**/*.txt",
            "**/*.html",
            "**/*.htm",
            "**/*.csv",
        ]

        excluded_patterns = [
            "**/.*",
            "**/*~",
            "**/*.tmp",
            "**/~$*",
        ]

        # Source: LocalFile with refresh safety net
        data_scope["files"] = flow_builder.add_source(
            cocoindex.sources.LocalFile(
                path=sync_dir,
                binary=True,
                included_patterns=included_patterns,
                excluded_patterns=excluded_patterns,
            ),
            refresh_interval=timedelta(hours=6),
        )

        collector = data_scope.add_collector()

        with data_scope["files"].row() as f:
            f["file_id"] = f["filename"].transform(file_id_from_filename)
            f["mime_type"] = f["filename"].transform(mime_type_from_filename)
            f["file_size"] = f["content"].transform(file_size_from_bytes)

            collector.collect(
                file_id=f["file_id"],
                source_path=f["filename"],
                file_name=f["filename"].transform(basename_from_filename),
                mime_type=f["mime_type"],
                file_size=f["file_size"],
            )

        collector.export(
            "unified_gdrive_export",
            QdrantHybridTargetSpec.from_config(config),
            primary_key_fields=["file_id"],
        )

    return cocoindex.open_flow(flow_name, flow_def)


def run_once(config: UnifiedConfig | None = None) -> None:
    """Run ingestion once (single pass)."""
    flow = build_flow(config)
    flow.setup()
    flow.update(print_stats=True)
    flow.close()


def run_watch(config: UnifiedConfig | None = None) -> None:
    """Run ingestion continuously using FlowLiveUpdater."""
    if config is None:
        config = UnifiedConfig()

    flow = build_flow(config)
    flow.setup()

    logger.info("Starting watch mode via CocoIndex FlowLiveUpdater")
    updater = cocoindex.FlowLiveUpdater(
        flow,
        cocoindex.FlowLiveUpdaterOptions(live_mode=True, print_stats=True),
    )
    try:
        updater.start()
        updater.wait()
    except KeyboardInterrupt:
        logger.info("Watch mode interrupted")
    finally:
        updater.abort()
        flow.close()
