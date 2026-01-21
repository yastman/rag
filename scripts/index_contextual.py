#!/usr/bin/env python3
"""
Index contextual JSON files into Qdrant.

Takes JSON files created by Claude CLI (with Contextual Retrieval)
and indexes them using the existing DocumentIndexer pipeline.

Usage:
    python scripts/index_contextual.py docs/processed/video1.json
    python scripts/index_contextual.py docs/processed/*.json --collection contextual_demo
    python scripts/index_contextual.py docs/processed/ --recreate
"""

import argparse
import asyncio
import sys
from pathlib import Path


# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Settings
from src.ingestion import DocumentIndexer, load_contextual_json


async def index_file(
    indexer: DocumentIndexer,
    json_path: Path,
    collection_name: str,
) -> dict:
    """Index a single contextual JSON file."""
    print(f"\nIndexing: {json_path.name}")

    # Load chunks from JSON
    chunks = load_contextual_json(str(json_path))
    print(f"  Loaded {len(chunks)} chunks")

    # Index chunks
    stats = await indexer.index_chunks(chunks, collection_name)

    return {
        "file": json_path.name,
        "total_chunks": stats.total_chunks,
        "indexed_chunks": stats.indexed_chunks,
        "failed_chunks": stats.failed_chunks,
    }


async def main(args: argparse.Namespace) -> int:
    """Main entry point."""
    print("\n" + "=" * 60)
    print("Contextual Retrieval Indexer")
    print("=" * 60)

    # Initialize
    settings = Settings()
    indexer = DocumentIndexer(settings)

    collection_name = args.collection or settings.collection_name
    print(f"\nCollection: {collection_name}")

    # Create collection if needed
    if args.recreate:
        print(f"Recreating collection: {collection_name}")
    await indexer.create_collection(collection_name, recreate=args.recreate)

    # Find JSON files
    input_path = Path(args.input)
    if input_path.is_file():
        json_files = [input_path]
    elif input_path.is_dir():
        json_files = list(input_path.glob("*.json"))
    else:
        # Glob pattern
        json_files = list(Path(".").glob(args.input))

    if not json_files:
        print(f"Error: No JSON files found: {args.input}")
        return 1

    print(f"Found {len(json_files)} JSON file(s)")

    # Index each file
    results = []
    for json_path in json_files:
        try:
            result = await index_file(indexer, json_path, collection_name)
            results.append(result)
        except Exception as e:
            print(f"  Error: {e}")
            results.append(
                {
                    "file": json_path.name,
                    "error": str(e),
                }
            )

    # Print summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    total_indexed = sum(r.get("indexed_chunks", 0) for r in results)
    total_failed = sum(r.get("failed_chunks", 0) for r in results)

    for r in results:
        if "error" in r:
            print(f"  {r['file']}: ERROR - {r['error']}")
        else:
            print(f"  {r['file']}: {r['indexed_chunks']} chunks indexed")

    print(f"\nTotal: {total_indexed} indexed, {total_failed} failed")

    # Print collection stats
    stats = await indexer.get_collection_stats(collection_name)
    if stats:
        print(f"\nCollection '{collection_name}': {stats.get('points_count', 0)} total points")

    return 0 if total_failed == 0 else 1


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Index contextual JSON files into Qdrant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "input",
        help="JSON file, directory, or glob pattern",
    )

    parser.add_argument(
        "--collection",
        "-c",
        help="Target collection name (default: from settings)",
    )

    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate collection if exists",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(asyncio.run(main(args)))
