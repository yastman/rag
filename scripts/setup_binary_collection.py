#!/usr/bin/env python3
"""
Setup Qdrant collection with Binary Quantization.

Creates a collection with BinaryQuantization for 32x compression and 40x faster search.
Uses *_binary suffix naming convention to distinguish from scalar quantized collections.

Usage:
    python scripts/setup_binary_collection.py
    python scripts/setup_binary_collection.py --source contextual_bulgaria_voyage
    python scripts/setup_binary_collection.py --force  # Recreate if exists
"""

import argparse
import os
import sys

from qdrant_client import QdrantClient
from qdrant_client.models import (
    BinaryQuantization,
    BinaryQuantizationConfig,
    Distance,
    HnswConfigDiff,
    Modifier,
    OptimizersConfigDiff,
    PayloadSchemaType,
    SparseVectorParams,
    VectorParams,
)


try:
    from scripts._qdrant_collection_setup import (
        collection_exists,
        delete_collection,
        get_qdrant_client,
        payload_index_types,
    )
    from scripts._qdrant_collection_setup import (
        create_payload_indexes as _create_payload_indexes,
    )
except ModuleNotFoundError:
    from _qdrant_collection_setup import (
        collection_exists,
        delete_collection,
        get_qdrant_client,
        payload_index_types,
    )
    from _qdrant_collection_setup import (
        create_payload_indexes as _create_payload_indexes,
    )


# Vector dimensions (Voyage voyage-4-large)
DENSE_DIMENSION = 1024


PAYLOAD_INDEX_FIELDS = (
    (
        PayloadSchemaType.KEYWORD,
        ("file_id", "metadata.file_id", "metadata.doc_id", "metadata.source"),
    ),
    (PayloadSchemaType.INTEGER, ("metadata.order", "metadata.chunk_order")),
    (
        PayloadSchemaType.KEYWORD,
        (
            "metadata.document_name",
            "metadata.doc_id",
            "metadata.article_number",
            "metadata.city",
            "metadata.source_type",
            "metadata.source",
            "metadata.topic",
            "metadata.doc_type",
            "metadata.jurisdiction",
            "metadata.audience",
            "metadata.language",
        ),
    ),
    (
        PayloadSchemaType.INTEGER,
        (
            "metadata.price",
            "metadata.rooms",
            "metadata.area",
            "metadata.floor",
            "metadata.floors",
            "metadata.distance_to_sea",
            "metadata.bathrooms",
            "metadata.chunk_id",
            "metadata.order",
        ),
    ),
    (PayloadSchemaType.BOOL, ("metadata.furnished", "metadata.year_round")),
)


def get_binary_collection_name(base_name: str) -> str:
    """Get the binary collection name from a base collection name."""
    if base_name.endswith("_binary"):
        return base_name
    return f"{base_name}_binary"


def create_binary_collection(client: QdrantClient, collection_name: str) -> None:
    """
    Create Qdrant collection with Binary Quantization.

    Binary Quantization benefits:
    - 32x compression ratio (each float32 → 1 bit)
    - 40x faster search (bitwise operations)
    - Best for high-dimensional vectors (1024-dim)
    - Requires rescoring for accuracy (automatically handled by Qdrant)

    Configuration:
    - always_ram=True: Quantized vectors in RAM for maximum speed
    - on_disk=True: Original vectors on disk for rescoring
    - Oversampling 2-4x recommended for accuracy
    """
    print(f"Creating binary quantized collection: {collection_name}")

    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            # Dense vectors with Binary Quantization (Voyage voyage-4-large)
            "dense": VectorParams(
                size=DENSE_DIMENSION,
                distance=Distance.COSINE,
                hnsw_config=HnswConfigDiff(
                    m=16,  # Edges per node: balance memory/quality
                    ef_construct=200,  # Build quality (higher = better graph)
                    on_disk=False,  # HNSW graph in RAM for fast traversal
                ),
                quantization_config=BinaryQuantization(
                    binary=BinaryQuantizationConfig(
                        always_ram=True,  # Quantized vectors in RAM (40x faster)
                    )
                ),
                on_disk=True,  # Original vectors on disk (for rescoring)
            ),
        },
        # BM42 sparse vectors (better than BM25 for short chunks)
        sparse_vectors_config={
            "bm42": SparseVectorParams(
                modifier=Modifier.IDF,  # Native IDF computation in Qdrant
            )
        },
        # Optimizer config for better bulk indexing
        optimizers_config=OptimizersConfigDiff(
            indexing_threshold=20000,  # Build HNSW every 20k vectors
            memmap_threshold=50000,  # Use mmap for segments >50k
        ),
    )

    print("  Created collection with Binary Quantization")
    print("  Vectors: dense (1024-dim, binary quantized)")
    print("  Sparse: bm42 (IDF modifier)")


def create_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    """Create this collection's payload indexes."""
    _create_payload_indexes(client, collection_name, PAYLOAD_INDEX_FIELDS)


def verify_collection_indexes(client: QdrantClient, collection_name: str) -> list[str]:
    """Verify required payload indexes exist.

    Returns:
        List of missing index names (empty if all present)
    """
    required_indexes = payload_index_types(PAYLOAD_INDEX_FIELDS)

    try:
        info = client.get_collection(collection_name)
        existing = info.payload_schema or {}

        missing = []
        for field, expected_type in required_indexes.items():
            if field not in existing:
                missing.append(field)
            else:
                # Check type matches
                actual_type = getattr(existing[field], "data_type", "unknown")
                if actual_type != expected_type:
                    missing.append(
                        f"{field} (wrong type: {actual_type}, expected: {expected_type})"
                    )

        return missing

    except Exception as e:
        return [f"Error checking collection: {e}"]


def verify_only(source_collection: str) -> bool:
    """Verify collection has required indexes without modifying.

    Returns:
        True if all required indexes present, False otherwise
    """
    try:
        client = get_qdrant_client()
        binary_collection = get_binary_collection_name(source_collection)

        if not collection_exists(client, binary_collection):
            print(f"Collection '{binary_collection}' does not exist.")
            return False

        missing = verify_collection_indexes(client, binary_collection)

        if missing:
            print(f"Collection '{binary_collection}' is MISSING required indexes:")
            for field in missing:
                print(f"  - {field}")
            print("\nRun without --verify-only to add missing indexes.")
            return False

        print(f"Collection '{binary_collection}' has all required indexes.")
        print_collection_info(client, binary_collection)
        return True

    except Exception as e:
        print(f"Error during verification: {e}")
        return False


def print_collection_info(client: QdrantClient, collection_name: str) -> None:
    """Print collection information."""
    try:
        info = client.get_collection(collection_name)
        print("\n" + "=" * 60)
        print(f"Collection: {collection_name}")
        print("=" * 60)
        print(f"  Status:         {info.status}")
        print(f"  Points count:   {info.points_count}")
        print(f"  Vectors count:  {getattr(info, 'vectors_count', 'n/a')}")

        # Vector config
        print("\n  Vector configurations:")
        vectors_config = info.config.params.vectors
        if isinstance(vectors_config, dict):
            for name, config in vectors_config.items():
                if hasattr(config, "size"):
                    quant_type = "binary" if hasattr(config, "quantization_config") else "none"
                    if config.quantization_config:
                        if hasattr(config.quantization_config, "binary"):
                            quant_type = "binary"
                        elif hasattr(config.quantization_config, "scalar"):
                            quant_type = "scalar (INT8)"
                    print(f"    - {name}: {config.size}-dim, {config.distance}, quant={quant_type}")
        elif vectors_config is not None and hasattr(vectors_config, "size"):
            print(
                f"    - default: {vectors_config.size}-dim, {vectors_config.distance}, quant=none"
            )

        # Sparse vectors
        if info.config.params.sparse_vectors:
            print("\n  Sparse vector configurations:")
            for name, sparse_config in info.config.params.sparse_vectors.items():
                modifier = getattr(sparse_config, "modifier", "none")
                print(f"    - {name}: modifier={modifier}")

        print("=" * 60 + "\n")

    except Exception as e:
        print(f"Error getting collection info: {e}")


def setup_binary_collection(
    source_collection: str,
    force: bool = False,
    skip_indexes: bool = False,
) -> bool:
    """
    Set up binary quantized Qdrant collection.

    Args:
        source_collection: Base collection name (will add _binary suffix)
        force: If True, recreate collection if it exists
        skip_indexes: If True, skip creating payload indexes

    Returns:
        True if successful, False otherwise
    """
    try:
        client = get_qdrant_client()

        # Check connection
        try:
            client.get_collections()
            print("  Connected successfully")
        except Exception as e:
            print(f"Error: Cannot connect to Qdrant: {e}")
            return False

        # Get binary collection name
        binary_collection = get_binary_collection_name(source_collection)

        # Handle existing collection
        if collection_exists(client, binary_collection):
            if force:
                delete_collection(client, binary_collection)
            else:
                print(f"Collection '{binary_collection}' already exists.")
                print("Use --force to recreate it.")
                print_collection_info(client, binary_collection)
                return True

        # Create collection
        create_binary_collection(client, binary_collection)

        # Create payload indexes
        if not skip_indexes:
            create_payload_indexes(client, binary_collection)

        # Print final info
        print_collection_info(client, binary_collection)

        print("Setup completed successfully!")
        return True

    except Exception as e:
        print(f"Error during setup: {e}")
        import traceback

        traceback.print_exc()
        return False


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Setup Qdrant collection with Binary Quantization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  QDRANT_URL      Qdrant server URL (default: http://localhost:6333)
  QDRANT_API_KEY  Optional API key for authentication

Examples:
  python scripts/setup_binary_collection.py
  python scripts/setup_binary_collection.py --source contextual_bulgaria_voyage
  python scripts/setup_binary_collection.py --force
  QDRANT_URL=http://qdrant:6333 python scripts/setup_binary_collection.py
        """,
    )

    parser.add_argument(
        "--source",
        "-s",
        default=os.getenv("COLLECTION_NAME", "gdrive_documents_bge"),
        help="Source collection name (will add _binary suffix)",
    )

    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force recreation of collection if it exists",
    )

    parser.add_argument(
        "--skip-indexes",
        action="store_true",
        help="Skip creating payload indexes",
    )

    parser.add_argument(
        "--verify-only",
        "-v",
        action="store_true",
        help="Only verify required indexes exist, don't modify collection",
    )

    args = parser.parse_args()

    # Handle verify-only mode
    if args.verify_only:
        print("\n" + "=" * 60)
        print("Qdrant Collection Verification")
        print("=" * 60 + "\n")
        success = verify_only(args.source)
        return 0 if success else 1

    print("\n" + "=" * 60)
    print("Qdrant Binary Quantization Collection Setup")
    print("=" * 60 + "\n")

    success = setup_binary_collection(
        source_collection=args.source,
        force=args.force,
        skip_indexes=args.skip_indexes,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
