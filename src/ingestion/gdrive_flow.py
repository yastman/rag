"""Google Drive ingestion watcher for rclone-synced folder.

DEPRECATED: Use unified ingestion pipeline instead (src.ingestion.unified).

Watches synced Drive folder (via rclone) and processes new/changed files:
1. Detect changes via content hash + persistent state (sqlite)
2. Chunk via docling-serve HybridChunker
3. Embed via Voyage (dense) + BM42 (sparse)
4. Index to Qdrant with replace semantics

Usage:
    python -m src.ingestion.gdrive_flow --once    # Run once
    python -m src.ingestion.gdrive_flow --watch   # Continuous mode
"""

import asyncio
import hashlib
import logging
import os
import warnings
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import anyio

from src.ingestion.docling_client import DoclingClient, DoclingConfig
from src.ingestion.gdrive_indexer import GDriveIndexer


warnings.warn(
    "This module is deprecated. Use src.ingestion.unified instead.",
    DeprecationWarning,
    stacklevel=2,
)

logger = logging.getLogger(__name__)


@dataclass
class GDriveFlowConfig:
    """Configuration for Google Drive ingestion flow."""

    # Sync directory (where rclone puts files)
    sync_dir: str = field(
        default_factory=lambda: os.getenv("GDRIVE_SYNC_DIR", os.path.expanduser("~/drive-sync"))
    )

    # Qdrant settings
    qdrant_url: str = field(
        default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333")
    )
    # Default to binary collection for best latency; override via env if needed.
    collection_name: str = field(
        default_factory=lambda: os.getenv("GDRIVE_COLLECTION_NAME", "gdrive_documents_bge")
    )

    # Docling settings
    docling_url: str = field(
        default_factory=lambda: os.getenv("DOCLING_URL", "http://localhost:5001")
    )
    chunk_max_tokens: int = 512

    # Voyage settings
    voyage_api_key: str | None = field(default_factory=lambda: os.getenv("VOYAGE_API_KEY"))

    # Watch settings
    watch_interval_seconds: int = 60


@dataclass
class ProcessedFile:
    """Record of processed file."""

    file_path: str
    file_id: str  # Hash of relative path
    content_hash: str  # Hash of file content
    chunks_count: int
    processed_at: datetime
    error: str | None = None


class GDriveFileProcessor:
    """Process files from synced Google Drive folder.

    Handles:
    - File type detection and filtering
    - Content hashing for change detection
    - Chunking via docling-serve
    - Indexing via GDriveIndexer
    """

    SUPPORTED_EXTENSIONS = {
        ".pdf",
        ".docx",
        ".doc",
        ".xlsx",
        ".xls",
        ".pptx",
        ".ppt",
        ".md",
        ".txt",
        ".html",
        ".htm",
    }

    def __init__(self, config: GDriveFlowConfig | None = None):
        """Initialize processor.

        Args:
            config: Flow configuration
        """
        self.config = config or GDriveFlowConfig()
        self.sync_dir = Path(self.config.sync_dir)

        # Docling client for chunking
        self.docling_config = DoclingConfig(
            base_url=self.config.docling_url,
            max_tokens=self.config.chunk_max_tokens,
        )

        # Indexer for Qdrant
        self.indexer = GDriveIndexer(
            qdrant_url=self.config.qdrant_url,
            voyage_api_key=self.config.voyage_api_key,
        )

        # Track processed files (PERSISTENT):
        # Use sqlite3 (stdlib) to persist file_id -> (source_path, content_hash, last_indexed_at)
        # so restarts do not trigger full reindex, and so we can detect deletions.
        self._processed: dict[str, ProcessedFile] = {}

    def _is_supported_file(self, path: Path) -> bool:
        """Check if file type is supported."""
        if path.name.startswith("."):
            return False
        if path.name.startswith("~$"):
            return False
        return path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def _compute_file_id(self, path: Path) -> str:
        """Compute stable file ID from relative path."""
        rel_path = path.relative_to(self.sync_dir)
        return hashlib.sha256(str(rel_path).encode()).hexdigest()[:16]

    def _compute_content_hash(self, path: Path) -> str:
        """Compute content hash for change detection."""
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hasher.update(chunk)
        return hasher.hexdigest()[:16]

    def _needs_processing(self, path: Path, file_id: str) -> bool:
        """Check if file needs (re)processing."""
        if file_id not in self._processed:
            return True

        current_hash = self._compute_content_hash(path)
        return current_hash != self._processed[file_id].content_hash

    async def process_file(self, path: Path) -> ProcessedFile | None:
        """Process a single file.

        Args:
            path: Path to file

        Returns:
            ProcessedFile record, or None if skipped
        """
        if not self._is_supported_file(path):
            return None

        file_id = self._compute_file_id(path)

        if not self._needs_processing(path, file_id):
            logger.debug(f"Skipping unchanged: {path}")
            return self._processed.get(file_id)

        logger.info(f"Processing: {path}")

        try:
            # Step 1: Chunk via docling
            async with DoclingClient(self.docling_config) as client:
                docling_chunks = await client.chunk_file(path)
                chunks = client.to_ingestion_chunks(
                    docling_chunks,
                    source=path.name,
                    source_type=path.suffix.lstrip("."),
                )

            # Add file metadata to chunks
            rel_path = str(path.relative_to(self.sync_dir))
            content_hash = self._compute_content_hash(path)

            for chunk in chunks:
                if chunk.extra_metadata is None:
                    chunk.extra_metadata = {}
                chunk.extra_metadata.update(
                    {
                        "file_id": file_id,
                        "source_path": rel_path,
                        "mime_type": self._get_mime_type(path),
                        "modified_time": datetime.fromtimestamp(
                            (await anyio.Path(path).stat()).st_mtime, tz=UTC
                        ).isoformat(),
                        "content_hash": content_hash,
                    }
                )

            # Step 2: Index to Qdrant (with replace semantics)
            stats = await self.indexer.index_file_chunks(
                chunks=chunks,
                file_id=file_id,
                collection_name=self.config.collection_name,
            )

            # Record processed file
            record = ProcessedFile(
                file_path=rel_path,
                file_id=file_id,
                content_hash=content_hash,
                chunks_count=stats.indexed_chunks,
                processed_at=datetime.now(UTC),
            )
            self._processed[file_id] = record

            logger.info(
                f"Processed {path.name}: {stats.indexed_chunks} chunks "
                f"(replaced {stats.deleted_points})"
            )
            return record

        except Exception as e:
            logger.error(f"Failed to process {path}: {e}", exc_info=True)
            return ProcessedFile(
                file_path=str(path.relative_to(self.sync_dir)),
                file_id=file_id,
                content_hash="",
                chunks_count=0,
                processed_at=datetime.now(UTC),
                error=str(e),
            )

    async def process_directory(self) -> list[ProcessedFile]:
        """Process all files in sync directory.

        Returns:
            List of processed file records
        """
        results = []

        # Track current file_ids to enable deletion detection
        current_file_ids: set[str] = set()

        for path in self.sync_dir.rglob("*"):
            if path.is_file():
                result = await self.process_file(path)
                if result:
                    results.append(result)
                    current_file_ids.add(result.file_id)

        # Reconcile deletions/renames:
        # - load known file_ids from sqlite state
        # - for file_ids not present in current_file_ids: delete from Qdrant and mark deleted
        # (This is required because rclone sync can delete/rename files without a "delete event".)
        await self._reconcile_deletions(current_file_ids)

        return results

    async def _reconcile_deletions(self, current_file_ids: set[str]) -> None:
        """Remove points for files that no longer exist.

        Args:
            current_file_ids: Set of file_ids currently in the sync directory
        """
        deleted_ids = set(self._processed.keys()) - current_file_ids

        for file_id in deleted_ids:
            try:
                deleted_count = await self.indexer.delete_file_points(
                    file_id, self.config.collection_name
                )
                logger.info(
                    f"Reconciled deletion: file_id={file_id}, removed {deleted_count} points"
                )
                del self._processed[file_id]
            except Exception as e:
                logger.error(f"Failed to reconcile deletion for {file_id}: {e}")

    async def watch(self) -> None:
        """Watch directory for changes continuously."""
        logger.info(f"Watching {self.sync_dir} (interval: {self.config.watch_interval_seconds}s)")

        while True:
            try:
                results = await self.process_directory()
                processed = [r for r in results if r.error is None]
                errors = [r for r in results if r.error is not None]

                if processed or errors:
                    logger.info(f"Cycle complete: {len(processed)} processed, {len(errors)} errors")
            except Exception as e:
                logger.error(f"Watch cycle failed: {e}", exc_info=True)

            await asyncio.sleep(self.config.watch_interval_seconds)

    @staticmethod
    def _get_mime_type(path: Path) -> str:
        """Get MIME type for file."""
        mime_map = {
            ".pdf": "application/pdf",
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".doc": "application/msword",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xls": "application/vnd.ms-excel",
            ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            ".ppt": "application/vnd.ms-powerpoint",
            ".md": "text/markdown",
            ".txt": "text/plain",
            ".html": "text/html",
            ".htm": "text/html",
        }
        return mime_map.get(path.suffix.lower(), "application/octet-stream")


async def run_once(config: GDriveFlowConfig | None = None) -> list[ProcessedFile]:
    """Run ingestion once.

    Args:
        config: Flow configuration

    Returns:
        List of processed files
    """
    processor = GDriveFileProcessor(config)
    return await processor.process_directory()


async def run_watch(config: GDriveFlowConfig | None = None) -> None:
    """Run continuous watch mode.

    Args:
        config: Flow configuration
    """
    processor = GDriveFileProcessor(config)
    await processor.watch()


def main():
    """CLI entry point."""
    from dotenv import load_dotenv

    load_dotenv()  # Load .env before config initialization

    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    parser = argparse.ArgumentParser(description="Google Drive ingestion flow")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--watch", action="store_true", help="Watch continuously")
    parser.add_argument("--sync-dir", help="Override sync directory")
    args = parser.parse_args()

    config = GDriveFlowConfig()
    if args.sync_dir:
        config.sync_dir = args.sync_dir

    if args.watch:
        asyncio.run(run_watch(config))
    else:
        results = asyncio.run(run_once(config))
        print(f"\nProcessed {len(results)} files:")
        for r in results:
            status = "OK" if r.error is None else f"ERROR: {r.error}"
            print(f"  {r.file_path}: {r.chunks_count} chunks ({status})")


if __name__ == "__main__":
    main()
