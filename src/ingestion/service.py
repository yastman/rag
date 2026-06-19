"""Ingestion service for document processing and indexing.

High-level service for ingesting documents from local directories
into Qdrant via the new orchestrator path.

Milestone J: Document Ingestion Pipeline (2026-02-02)
CocoIndex removed: #2834.
"""

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse


logger = logging.getLogger(__name__)


@dataclass
class IngestionStats:
    """Statistics from an ingestion operation."""

    total_documents: int = 0
    total_nodes: int = 0
    indexed_nodes: int = 0
    skipped_nodes: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)


class IngestionService:
    """High-level service for document ingestion.

    Wraps CocoIndex flows to provide a simple API for ingesting
    documents from various sources into Qdrant.

    Example:
        service = IngestionService(collection_name="my_docs")
        stats = await service.ingest_directory(Path("/path/to/docs"))
        print(f"Indexed {stats.indexed_nodes} chunks")
        await service.close()
    """

    def __init__(
        self,
        qdrant_url: str | None = None,
        qdrant_api_key: str | None = None,
        collection_name: str = "documents",
        chunk_size: int = 512,
        chunk_overlap: int = 50,
    ):
        """Initialize ingestion service.

        Args:
            qdrant_url: Qdrant server URL (defaults to QDRANT_URL env var)
            qdrant_api_key: Qdrant API key (defaults to QDRANT_API_KEY env var)
            collection_name: Target Qdrant collection name
            chunk_size: Tokens per chunk
            chunk_overlap: Overlap between chunks
        """
        resolved_qdrant_url = qdrant_url or os.getenv("QDRANT_URL")
        self.qdrant_url: str = resolved_qdrant_url or "http://localhost:6333"
        self.qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY")
        self.collection_name = collection_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

        # Google Drive ingestion has been removed. The service no longer
        # initialises a google_service_account_key. See issue #2835.

        # Qdrant client for stats
        self._qdrant_client: QdrantClient | None = None

        logger.info(
            f"IngestionService initialized: collection={collection_name}, qdrant={self.qdrant_url}"
        )

    @property
    def qdrant_client(self) -> QdrantClient:
        """Lazy-load Qdrant client."""
        if self._qdrant_client is None:
            if self.qdrant_api_key:
                self._qdrant_client = QdrantClient(
                    url=self.qdrant_url,
                    api_key=self.qdrant_api_key,
                    timeout=60,
                )
            else:
                self._qdrant_client = QdrantClient(
                    url=self.qdrant_url,
                    timeout=60,
                )
        return self._qdrant_client

    def _create_flow_config(self) -> dict:
        """Return service settings as a plain dict (CocoIndex removed, #2834)."""
        return {
            "qdrant_url": self.qdrant_url,
            "qdrant_api_key": self.qdrant_api_key,
            "collection_name": self.collection_name,
        }

    async def ingest_directory(self, directory: Path) -> IngestionStats:
        """Ingest documents from a local directory.

        CocoIndex has been removed (#2834). Use the UnifiedIngestionOrchestrator
        with INGEST_USE_NEW_ORCHESTRATOR=true for ingestion.

        Args:
            directory: Path to directory containing documents

        Returns:
            IngestionStats with counts and timing
        """
        start_time = time.time()
        stats = IngestionStats()

        if not await anyio.Path(directory).exists():
            stats.errors.append(f"Directory not found: {directory}")
            return stats

        # Count documents
        supported_extensions = {".pdf", ".docx", ".doc", ".md", ".txt", ".html", ".htm"}
        documents = await anyio.to_thread.run_sync(
            lambda: [
                Path(entry.path)
                for entry in os.scandir(directory)
                if entry.is_file() and Path(entry.path).suffix.lower() in supported_extensions
            ]
        )
        stats.total_documents = len(documents)

        if stats.total_documents == 0:
            stats.errors.append(f"No supported documents found in {directory}")
            return stats

        logger.info(f"Ingesting {stats.total_documents} documents from {directory}")
        stats.errors.append(
            "CocoIndex has been removed (#2834). "
            "Use UnifiedIngestionOrchestrator with INGEST_USE_NEW_ORCHESTRATOR=true."
        )

        stats.duration_seconds = time.time() - start_time
        return stats

    # ingest_gdrive() has been deliberately removed. Historically this service
    # exposed an ingest_gdrive() coroutine to ingest documents directly from
    # Google Drive using a service account key. The implementation never
    # materialised and the stub merely returned a "not yet implemented" error.
    # As part of cleaning up vestigial Google/GDrive support (see issue #2835),
    # the google_service_account_key attribute and ingest_gdrive() API have
    # been removed. Calls to this method will now result in an AttributeError.

    async def get_collection_stats(self) -> dict[str, Any]:
        """Get statistics for the target collection.

        Returns:
            Dict with collection info (name, points_count, status, etc.)
        """
        try:
            info = self.qdrant_client.get_collection(self.collection_name)
            return {
                "name": self.collection_name,
                "points_count": info.points_count,
                "vectors_count": getattr(info, "vectors_count", info.indexed_vectors_count),
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": str(info.status),
            }
        except UnexpectedResponse as e:
            if "not found" in str(e).lower():
                return {
                    "name": self.collection_name,
                    "error": "Collection not found",
                    "points_count": 0,
                }
            return {
                "name": self.collection_name,
                "error": str(e),
                "points_count": 0,
            }
        except Exception as e:
            if "not found" in str(e).lower() or getattr(e, "status_code", None) == 404:
                return {
                    "name": self.collection_name,
                    "error": "Collection not found",
                    "points_count": 0,
                }
            logger.error(f"Error getting collection stats: {e}")
            return {
                "name": self.collection_name,
                "error": str(e),
                "points_count": 0,
            }

    async def close(self) -> None:
        """Close service connections."""
        if self._qdrant_client is not None:
            self._qdrant_client.close()
            self._qdrant_client = None
        logger.info("IngestionService closed")


# Convenience functions for CLI and Makefile integration


async def ingest_from_directory(
    directory: str | Path,
    collection_name: str = "documents",
) -> IngestionStats:
    """Convenience function to ingest from a directory.

    Args:
        directory: Path to directory
        collection_name: Target collection name

    Returns:
        IngestionStats
    """
    service = IngestionService(collection_name=collection_name)
    try:
        return await service.ingest_directory(Path(directory))
    finally:
        await service.close()


async def ingest_from_gdrive(
    folder_id: str,
    collection_name: str = "documents",
) -> IngestionStats:
    """Convenience function to ingest from Google Drive.

    This helper previously delegated to ``IngestionService.ingest_gdrive`` to
    ingest documents directly from a Google Drive folder. As part of issue
    #2835, Google Drive ingestion has been removed and this function is now
    deprecated. It will raise a ``NotImplementedError`` if called.

    Args:
        folder_id: Google Drive folder ID
        collection_name: Target collection name

    Returns:
        IngestionStats (never actually returned; function raises instead)
    """
    raise NotImplementedError(
        "Google Drive ingestion has been removed (see issue #2835). "
        "Use ingest_from_directory() with a local sync directory instead."
    )


async def get_ingestion_status(collection_name: str = "documents") -> dict[str, Any]:
    """Get ingestion status for a collection.

    Args:
        collection_name: Collection name

    Returns:
        Collection statistics
    """
    service = IngestionService(collection_name=collection_name)
    try:
        return await service.get_collection_stats()
    finally:
        await service.close()
