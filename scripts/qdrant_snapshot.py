#!/usr/bin/env python3
"""Qdrant snapshot backup script.

Creates and downloads snapshots for Qdrant collections.
Supports backing up specific collections or all collections at once.

Usage:
    # Backup all collections
    python scripts/qdrant_snapshot.py

    # Backup specific collections
    python scripts/qdrant_snapshot.py --collections gdrive_documents_bge legal_documents

    # Custom output directory and URL
    python scripts/qdrant_snapshot.py --output-dir /tmp/backups --url http://qdrant:6333

    # Dry run (list collections only)
    python scripts/qdrant_snapshot.py --dry-run
"""

import argparse
import asyncio
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from qdrant_client import AsyncQdrantClient


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_OUTPUT_DIR = "/backups"


async def get_all_collections(client: AsyncQdrantClient) -> list[str]:
    """Fetch all collection names from Qdrant.

    Args:
        client: Async Qdrant client instance.

    Returns:
        Sorted list of collection names.
    """
    response = await client.get_collections()
    return sorted(c.name for c in response.collections)


async def create_and_download_snapshot(
    client: AsyncQdrantClient,
    collection_name: str,
    output_dir: Path,
    qdrant_url: str,
    api_key: str | None = None,
) -> Path | None:
    """Create a snapshot for a collection and download it.

    Args:
        client: Async Qdrant client instance.
        collection_name: Name of the collection to snapshot.
        output_dir: Directory to save the snapshot file.
        qdrant_url: Base URL of the Qdrant server (for download).
        api_key: Optional API key for authentication.

    Returns:
        Path to the downloaded snapshot file, or None on failure.
    """
    # Create snapshot
    logger.info("Creating snapshot for '%s'...", collection_name)
    try:
        snapshot_info = await client.create_snapshot(collection_name=collection_name)
    except Exception:
        logger.exception("Failed to create snapshot for '%s'", collection_name)
        return None

    if snapshot_info is None:
        logger.error("Snapshot creation returned None for '%s'", collection_name)
        return None

    snapshot_name = snapshot_info.name
    logger.info("Snapshot created: %s", snapshot_name)

    # Build download URL
    snapshot_url = f"{qdrant_url}/collections/{collection_name}/snapshots/{snapshot_name}"

    # Download snapshot via httpx (streaming for large files)
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    local_filename = f"{collection_name}-{timestamp}.snapshot"
    local_path = output_dir / local_filename

    logger.info("Downloading snapshot to %s ...", local_path)

    headers = {}
    if api_key:
        headers["api-key"] = api_key

    try:
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as http_client,
            http_client.stream("GET", snapshot_url, headers=headers) as response,
        ):
            response.raise_for_status()
            total_bytes = 0
            with open(local_path, "wb") as f:
                async for chunk in response.aiter_bytes(chunk_size=8192):
                    f.write(chunk)
                    total_bytes += len(chunk)

        size_mb = total_bytes / (1024 * 1024)
        logger.info("Downloaded %s (%.1f MB)", local_filename, size_mb)
        return local_path

    except Exception:
        logger.exception("Failed to download snapshot for '%s'", collection_name)
        # Clean up partial file
        if local_path.exists():
            local_path.unlink()
        return None


async def run_backup(
    qdrant_url: str,
    api_key: str | None,
    collections: list[str] | None,
    output_dir: Path,
    dry_run: bool = False,
) -> int:
    """Run the backup process for specified collections.

    Args:
        qdrant_url: Qdrant server URL.
        api_key: Optional API key.
        collections: List of collection names, or None for all.
        output_dir: Directory to save snapshots.
        dry_run: If True, only list collections without creating snapshots.

    Returns:
        Exit code (0 = success, 1 = partial failure, 2 = total failure).
    """
    client = AsyncQdrantClient(url=qdrant_url, api_key=api_key)

    try:
        # Get collection list
        all_collections = await get_all_collections(client)
        if not all_collections:
            logger.warning("No collections found in Qdrant at %s", qdrant_url)
            return 2

        logger.info("Available collections: %s", ", ".join(all_collections))

        # Determine which collections to back up
        if collections:
            target_collections = []
            for name in collections:
                if name in all_collections:
                    target_collections.append(name)
                else:
                    logger.warning("Collection '%s' not found, skipping", name)
            if not target_collections:
                logger.error("None of the specified collections exist")
                return 2
        else:
            target_collections = all_collections

        logger.info("Collections to backup: %s", ", ".join(target_collections))

        if dry_run:
            logger.info("Dry run — no snapshots created")
            for name in target_collections:
                info = await client.get_collection(name)
                logger.info(
                    "  %s: %d points, %d indexed vectors",
                    name,
                    info.points_count or 0,
                    info.indexed_vectors_count or 0,
                )
            return 0

        # Ensure output directory exists
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Output directory: %s", output_dir)

        # Create and download snapshots
        success_count = 0
        failed: list[str] = []

        for name in target_collections:
            result = await create_and_download_snapshot(
                client=client,
                collection_name=name,
                output_dir=output_dir,
                qdrant_url=qdrant_url,
                api_key=api_key,
            )
            if result:
                success_count += 1
            else:
                failed.append(name)

        # Summary
        logger.info("Backup complete: %d/%d succeeded", success_count, len(target_collections))
        if failed:
            logger.warning("Failed collections: %s", ", ".join(failed))
            return 1

        return 0

    finally:
        await client.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Create and download Qdrant collection snapshots.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                  # Backup all collections
  %(prog)s --collections gdrive_documents_bge legal_documents
  %(prog)s --output-dir /tmp/backups --url http://qdrant:6333
  %(prog)s --dry-run                        # List collections only
        """,
    )
    parser.add_argument(
        "--collections",
        nargs="+",
        default=None,
        help="Collection names to backup (default: all)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.getenv("QDRANT_BACKUP_DIR", DEFAULT_OUTPUT_DIR),
        help=f"Directory to save snapshots (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL),
        help=f"Qdrant server URL (default: {DEFAULT_QDRANT_URL})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List collections and stats without creating snapshots",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the Qdrant snapshot backup script.

    Args:
        argv: Optional argument list (defaults to sys.argv).

    Returns:
        Exit code.
    """
    args = parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    api_key = os.getenv("QDRANT_API_KEY")
    output_dir = Path(args.output_dir)

    logger.info("Qdrant URL: %s", args.url)
    logger.info("Output dir: %s", output_dir)

    return asyncio.run(
        run_backup(
            qdrant_url=args.url,
            api_key=api_key,
            collections=args.collections,
            output_dir=output_dir,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
