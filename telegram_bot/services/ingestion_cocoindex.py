"""CocoIndex-based ingestion service.

High-level service for ingesting documents from local directories
and Google Drive into Qdrant using CocoIndex flows.

Milestone J: Document Ingestion Pipeline (2026-02-02)
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from src.ingestion.service import (
    IngestionService,
    IngestionStats,
)
from src.ingestion.service import (
    get_ingestion_status as _get_ingestion_status,
)
from src.ingestion.service import (
    ingest_from_directory as _ingest_from_directory,
)
from src.ingestion.service import (
    ingest_from_gdrive as _ingest_from_gdrive,
)


logger = logging.getLogger(__name__)


# Re-export with CocoIndex naming
class CocoIndexIngestionStats(IngestionStats):
    """Alias for IngestionStats."""


class CocoIndexIngestionService(IngestionService):
    """CocoIndex-based ingestion service.

    Uses CocoIndex flows for document processing and Voyage AI for embeddings.
    """


# Convenience functions
async def ingest_from_directory(
    directory: str | Path,
    collection_name: str = "documents",
) -> IngestionStats:
    """Ingest documents from a local directory."""
    return await _ingest_from_directory(directory, collection_name)


async def ingest_from_gdrive(
    folder_id: str,
    collection_name: str = "documents",
) -> IngestionStats:
    """Ingest documents from Google Drive."""
    return await _ingest_from_gdrive(folder_id, collection_name)


async def get_ingestion_status(collection_name: str = "documents") -> dict[str, Any]:
    """Get collection status."""
    return await _get_ingestion_status(collection_name)


def main() -> int:
    """CLI entry point for Makefile integration.

    Returns the process exit code (0 on success, 1 on usage error or unknown
    command) rather than calling ``sys.exit`` from inside the function body
    (#1072). Single ``sys.exit(main())`` lives at the ``__main__`` guard so
    the function is testable in-process and any caller that imports
    :func:`main` cannot accidentally terminate its host interpreter.
    """
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python -m telegram_bot.services.ingestion_cocoindex ingest-dir <path>")
        print("  python -m telegram_bot.services.ingestion_cocoindex ingest-gdrive <folder_id>")
        print("  python -m telegram_bot.services.ingestion_cocoindex status")
        return 1

    command = sys.argv[1]

    if command == "ingest-dir":
        if len(sys.argv) < 3:
            print("Error: Directory path required")
            return 1
        directory = sys.argv[2]
        stats = asyncio.run(ingest_from_directory(directory))
        print("\nIngestion complete:")
        print(f"  Documents: {stats.total_documents}")
        print(f"  Nodes: {stats.indexed_nodes}")
        print(f"  Duration: {stats.duration_seconds:.2f}s")
        if stats.errors:
            print(f"  Errors: {stats.errors}")
        return 0

    if command == "ingest-gdrive":
        if len(sys.argv) < 3:
            print("Error: Folder ID required")
            return 1
        folder_id = sys.argv[2]
        stats = asyncio.run(ingest_from_gdrive(folder_id))
        print("\nIngestion complete:")
        print(f"  Documents: {stats.total_documents}")
        print(f"  Nodes: {stats.indexed_nodes}")
        print(f"  Duration: {stats.duration_seconds:.2f}s")
        if stats.errors:
            print(f"  Errors: {stats.errors}")
        return 0

    if command == "status":
        status = asyncio.run(get_ingestion_status())
        print("\nCollection status:")
        for key, value in status.items():
            print(f"  {key}: {value}")
        return 0

    print(f"Unknown command: {command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
