#!/usr/bin/env python3
"""
Setup Qdrant collection for local development.

Creates a collection with optimized vector configuration for RAG:
- Dense vectors (1024-dim) with Binary Quantization (40x faster search)
- ColBERT multivectors for reranking
- BM42 sparse vectors with IDF modifier

Usage:
    python scripts/setup_qdrant_collection.py
    python scripts/setup_qdrant_collection.py --force  # Recreate if exists
    python scripts/setup_qdrant_collection.py --collection my_collection
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
    MultiVectorComparator,
    MultiVectorConfig,
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
    )
    from scripts._qdrant_collection_setup import (
        create_payload_indexes as _create_payload_indexes,
    )
except ModuleNotFoundError:
    from _qdrant_collection_setup import (
        collection_exists,
        delete_collection,
        get_qdrant_client,
    )
    from _qdrant_collection_setup import (
        create_payload_indexes as _create_payload_indexes,
    )


# Vector dimensions (BGE-M3)
DENSE_DIMENSION = 1024


PAYLOAD_INDEX_FIELDS = (
    (
        PayloadSchemaType.KEYWORD,
        (
            "file_id",
            "metadata.file_id",
            "metadata.doc_id",
            "metadata.source",
            "metadata.file_name",
            "metadata.mime_type",
            "metadata.topic",
            "metadata.doc_type",
        ),
    ),
    (PayloadSchemaType.INTEGER, ("metadata.order", "metadata.chunk_id")),
)


def create_collection(client: QdrantClient, collection_name: str) -> None:
    """
    Create Qdrant collection with optimized vector configuration.

    Configuration based on Qdrant best practices:
    - Binary quantization: 32x compression, 40x faster search
    - BM42 sparse vectors: +9% Precision@10 vs BM25 for short chunks
    - Original vectors on disk: RAM savings with fast rescoring
    - HNSW optimized: m=16 (balance), ef_construct=200 (quality)
    """
    print(f"Creating collection: {collection_name}")

    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            # Dense vectors for semantic search (BGE-M3)
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
                on_disk=True,  # Original vectors on disk (RAM savings + rescoring)
            ),
            # ColBERT multivector for reranking
            "colbert": VectorParams(
                size=DENSE_DIMENSION,
                distance=Distance.COSINE,
                multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                hnsw_config=HnswConfigDiff(
                    m=0,  # Disable HNSW for ColBERT (only for reranking)
                ),
                on_disk=True,  # ColBERT vectors on disk (only used for rerank)
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

    print("  Created collection with vectors: dense, colbert, bm42")


def create_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    """Create this collection's payload indexes."""
    _create_payload_indexes(client, collection_name, PAYLOAD_INDEX_FIELDS)


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
                    print(f"    - {name}: {config.size}-dim, {config.distance}")
        elif vectors_config is not None and hasattr(vectors_config, "size"):
            print(f"    - default: {vectors_config.size}-dim, {vectors_config.distance}")

        # Sparse vectors
        if info.config.params.sparse_vectors:
            print("\n  Sparse vector configurations:")
            for name, sparse_config in info.config.params.sparse_vectors.items():
                modifier = getattr(sparse_config, "modifier", "none")
                print(f"    - {name}: modifier={modifier}")

        # Payload indexes
        if hasattr(info, "payload_schema") and info.payload_schema:
            print("\n  Payload indexes:")
            for field, schema in info.payload_schema.items():
                print(f"    - {field}: {schema.data_type}")

        print("=" * 60 + "\n")

    except Exception as e:
        print(f"Error getting collection info: {e}")


def setup_collection(
    collection_name: str,
    force: bool = False,
    skip_indexes: bool = False,
) -> bool:
    """
    Set up Qdrant collection for RAG.

    Args:
        collection_name: Name of the collection to create
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

        # Handle existing collection
        if collection_exists(client, collection_name):
            if force:
                delete_collection(client, collection_name)
            else:
                print(f"Collection '{collection_name}' already exists.")
                print("Use --force to recreate it.")
                print_collection_info(client, collection_name)
                return True

        # Create collection
        create_collection(client, collection_name)

        # Create payload indexes
        if not skip_indexes:
            create_payload_indexes(client, collection_name)

        # Print final info
        print_collection_info(client, collection_name)

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
        description="Setup Qdrant collection for local development",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Environment variables:
  QDRANT_URL      Qdrant server URL (default: http://localhost:6333)
  QDRANT_API_KEY  Optional API key for authentication
  COLLECTION_NAME Default collection name (default: gdrive_documents_bge)

Examples:
  python scripts/setup_qdrant_collection.py
  python scripts/setup_qdrant_collection.py --force
  python scripts/setup_qdrant_collection.py --collection my_docs --force
  QDRANT_URL=http://qdrant:6333 python scripts/setup_qdrant_collection.py
        """,
    )

    parser.add_argument(
        "--collection",
        "-c",
        default=os.getenv("COLLECTION_NAME", "gdrive_documents_bge"),
        help="Collection name (default: gdrive_documents_bge or COLLECTION_NAME env)",
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

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("Qdrant Collection Setup")
    print("=" * 60 + "\n")

    success = setup_collection(
        collection_name=args.collection,
        force=args.force,
        skip_indexes=args.skip_indexes,
    )

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
