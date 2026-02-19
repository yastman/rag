#!/usr/bin/env python3
"""
Reindex from scalar-quantized collection to binary-quantized collection.

Scrolls through source collection and copies all vectors to binary collection.
Does NOT re-embed - copies existing vectors directly (fast, no API calls).

Usage:
    python scripts/reindex_to_binary.py
    python scripts/reindex_to_binary.py --source contextual_bulgaria_voyage
    python scripts/reindex_to_binary.py --batch-size 500
"""

import argparse
import os
import sys
import time
from dataclasses import dataclass

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

# Import collection setup from sibling script
from setup_binary_collection import (
    collection_exists,
    create_binary_collection,
    create_payload_indexes,
    get_binary_collection_name,
    print_collection_info,
)


@dataclass
class ReindexStats:
    """Reindexing statistics."""

    total_points: int = 0
    indexed_points: int = 0
    failed_points: int = 0
    duration_seconds: float = 0.0


def get_qdrant_client() -> QdrantClient:
    """Create Qdrant client from environment variables."""
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY")

    return QdrantClient(
        url=url,
        api_key=api_key,
        timeout=120,  # Longer timeout for batch operations
    )


def get_source_collection_info(client: QdrantClient, collection_name: str) -> dict:
    """Get source collection metadata."""
    try:
        info = client.get_collection(collection_name)
        return {
            "name": collection_name,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "status": str(info.status),
        }
    except Exception as e:
        print(f"Error getting collection info: {e}")
        return {}


def reindex_to_binary(
    source_collection: str,
    batch_size: int = 100,
    force: bool = False,
    skip_indexes: bool = False,
) -> ReindexStats:
    """
    Reindex from scalar to binary quantized collection.

    Args:
        source_collection: Source collection name (scalar quantized)
        batch_size: Number of points to process per batch
        force: If True, recreate target collection if exists
        skip_indexes: If True, skip creating payload indexes

    Returns:
        Reindexing statistics
    """
    stats = ReindexStats()
    start_time = time.time()

    client = get_qdrant_client()

    # Verify source collection exists
    if not collection_exists(client, source_collection):
        print(f"Error: Source collection '{source_collection}' does not exist")
        return stats

    # Get source collection info
    source_info = get_source_collection_info(client, source_collection)
    print(f"\nSource collection: {source_collection}")
    print(f"  Points: {source_info.get('points_count', 'unknown')}")
    print(f"  Status: {source_info.get('status', 'unknown')}")

    stats.total_points = source_info.get("points_count", 0)

    # Get/create target collection
    target_collection = get_binary_collection_name(source_collection)
    print(f"\nTarget collection: {target_collection}")

    if collection_exists(client, target_collection):
        if force:
            print("  Deleting existing collection...")
            client.delete_collection(target_collection)
        else:
            print("  Collection already exists. Use --force to recreate.")
            return stats

    # Create binary collection
    create_binary_collection(client, target_collection)
    if not skip_indexes:
        create_payload_indexes(client, target_collection)

    # Scroll through source and copy to target
    print(f"\nReindexing {stats.total_points} points in batches of {batch_size}...")

    offset: str | None = None
    batch_num = 0

    while True:
        # Scroll source collection
        results = client.scroll(
            collection_name=source_collection,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )

        points, next_offset = results

        if not points:
            break

        batch_num += 1

        # Convert to PointStruct for upsert
        try:
            # Build points for upsert
            upsert_points = []
            for point in points:
                # Handle different vector formats
                vectors = point.vector

                # Skip if no dense vector
                if not vectors or "dense" not in vectors:
                    stats.failed_points += 1
                    continue

                # Build point with only dense and bm42 (no colbert for Voyage)
                point_vectors = {"dense": vectors["dense"]}
                if "bm42" in vectors:
                    point_vectors["bm42"] = vectors["bm42"]

                upsert_points.append(
                    PointStruct(
                        id=point.id,
                        vector=point_vectors,
                        payload=point.payload,
                    )
                )

            # Upsert to target collection
            if upsert_points:
                client.upsert(
                    collection_name=target_collection,
                    points=upsert_points,
                )
                stats.indexed_points += len(upsert_points)

            # Progress
            progress_pct = (
                (stats.indexed_points / stats.total_points * 100) if stats.total_points > 0 else 0
            )
            print(
                f"  Batch {batch_num}: {stats.indexed_points}/{stats.total_points} "
                f"({progress_pct:.1f}%)"
            )

        except Exception as e:
            print(f"  Error in batch {batch_num}: {e}")
            stats.failed_points += len(points)

        # Next batch
        offset = next_offset
        if offset is None:
            break

    stats.duration_seconds = time.time() - start_time

    # Print summary
    print("\n" + "=" * 60)
    print("Reindexing Complete")
    print("=" * 60)
    print(f"  Total points:   {stats.total_points}")
    print(f"  Indexed:        {stats.indexed_points}")
    print(f"  Failed:         {stats.failed_points}")
    print(f"  Duration:       {stats.duration_seconds:.2f}s")
    print(f"  Rate:           {stats.indexed_points / stats.duration_seconds:.1f} points/sec")

    # Print target collection info
    print_collection_info(client, target_collection)

    return stats


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Reindex from scalar to binary quantized collection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  QDRANT_URL      Qdrant server URL (default: http://localhost:6333)
  QDRANT_API_KEY  Optional API key for authentication

Examples:
  python scripts/reindex_to_binary.py
  python scripts/reindex_to_binary.py --source contextual_bulgaria_voyage
  python scripts/reindex_to_binary.py --batch-size 500 --force
        """,
    )

    parser.add_argument(
        "--source",
        "-s",
        default=os.getenv("COLLECTION_NAME", "gdrive_documents_bge"),
        help="Source collection name (scalar quantized)",
    )

    parser.add_argument(
        "--batch-size",
        "-b",
        type=int,
        default=100,
        help="Number of points per batch (default: 100)",
    )

    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force recreation of target collection if it exists",
    )

    parser.add_argument(
        "--skip-indexes",
        action="store_true",
        help="Skip creating payload indexes",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("Qdrant Scalar → Binary Reindexing")
    print("=" * 60)

    stats = reindex_to_binary(
        source_collection=args.source,
        batch_size=args.batch_size,
        force=args.force,
        skip_indexes=args.skip_indexes,
    )

    # Return non-zero if any failures
    if stats.failed_points > 0:
        return 1
    if stats.indexed_points == 0:
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
