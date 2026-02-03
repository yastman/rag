# src/ingestion/unified/flow.py
"""CocoIndex flow for unified ingestion pipeline.

Uses sources.LocalFile for change detection and exports to QdrantHybridTarget.
"""

import hashlib
import logging
from pathlib import Path

import cocoindex

from src.ingestion.unified.config import UnifiedConfig
from src.ingestion.unified.targets.qdrant_hybrid_target import (
    QdrantHybridTargetConnector,  # noqa: F401 - registers the connector
    QdrantHybridTargetSpec,
    QdrantHybridTargetValues,
)


logger = logging.getLogger(__name__)


# MIME types for supported extensions
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


def get_mime_type(file_path: str) -> str:
    """Get MIME type from file extension."""
    ext = Path(file_path).suffix.lower()
    return MIME_TYPES.get(ext, "application/octet-stream")


@cocoindex.flow_def(name="unified_ingestion")
def unified_ingestion_flow(flow_builder: cocoindex.FlowBuilder, config: UnifiedConfig) -> None:
    """Define the unified ingestion flow.

    Flow:
    1. sources.LocalFile watches sync_dir for changes
    2. Collector extracts file metadata
    3. Export to QdrantHybridTarget for processing
    """
    sync_dir = str(config.sync_dir)

    # Supported file patterns
    included_patterns = [
        "**/*.pdf",
        "**/*.docx",
        "**/*.doc",
        "**/*.xlsx",
        "**/*.pptx",
        "**/*.md",
        "**/*.txt",
        "**/*.html",
        "**/*.htm",
        "**/*.csv",
    ]

    # Exclude hidden files and temp files
    excluded_patterns = [
        "**/.*",
        "**/*~",
        "**/*.tmp",
        "**/~$*",
    ]

    # Source: LocalFile with change detection
    files = flow_builder.source(
        cocoindex.sources.LocalFile(
            path=sync_dir,
            included_patterns=included_patterns,
            excluded_patterns=excluded_patterns,
            binary=True,  # Get file content as bytes
        )
    )

    # Collector: extract metadata and compute file_id
    @cocoindex.op.collector()
    class FileCollector:
        """Collect file metadata for export."""

        file_id: cocoindex.String
        abs_path: cocoindex.String
        source_path: cocoindex.String
        file_name: cocoindex.String
        mime_type: cocoindex.String
        file_size: cocoindex.Int64

    collected = files.transform(
        FileCollector,
        lambda row: FileCollector(
            file_id=compute_file_id(row["filename"]),
            abs_path=str(Path(sync_dir) / row["filename"]),
            source_path=row["filename"],
            file_name=Path(row["filename"]).name,
            mime_type=get_mime_type(row["filename"]),
            file_size=len(row["content"]) if row["content"] else 0,
        ),
    )

    # Export to Qdrant via custom target
    target_spec = QdrantHybridTargetSpec.from_config(config)

    collected.export(
        target_spec,
        primary_key=["file_id"],
        value_fields={
            "abs_path": QdrantHybridTargetValues.abs_path,
            "source_path": QdrantHybridTargetValues.source_path,
            "file_name": QdrantHybridTargetValues.file_name,
            "mime_type": QdrantHybridTargetValues.mime_type,
            "file_size": QdrantHybridTargetValues.file_size,
        },
    )


def build_flow(config: UnifiedConfig | None = None) -> cocoindex.Flow:
    """Build and return the unified ingestion flow.

    Args:
        config: Pipeline configuration. Uses defaults if not provided.

    Returns:
        CocoIndex Flow instance.
    """
    if config is None:
        config = UnifiedConfig()

    # Initialize CocoIndex with Postgres backend
    cocoindex.init(
        database_url=config.database_url,
    )

    # Build flow
    return cocoindex.open_flow(
        unified_ingestion_flow,
        config=config,
    )


def run_once(config: UnifiedConfig | None = None) -> None:
    """Run ingestion once (single pass).

    Args:
        config: Pipeline configuration.
    """
    _flow = build_flow(config)

    # Setup and update
    cocoindex.setup_all_flows()
    cocoindex.update_all_flows()

    logger.info("Single pass completed")


def run_watch(config: UnifiedConfig | None = None) -> None:
    """Run continuous ingestion with live updates.

    Args:
        config: Pipeline configuration.
    """
    flow = build_flow(config)

    # Setup
    cocoindex.setup_all_flows()

    # Live updater for continuous watching
    logger.info(f"Starting watch mode: {config.sync_dir if config else 'default'}")

    updater = cocoindex.FlowLiveUpdater(
        flow,
        cocoindex.FlowLiveUpdaterOptions(
            live_mode=True,
            print_stats=True,
        ),
    )

    try:
        updater.start()
        updater.wait()
    except KeyboardInterrupt:
        logger.info("Watch mode interrupted")
    finally:
        updater.stop()
