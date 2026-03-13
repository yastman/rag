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
from qdrant_client.http.exceptions import UnexpectedResponse
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


# Vector dimensions (BGE-M3)
DENSE_DIMENSION = 1024


def get_qdrant_client() -> QdrantClient:
    """Create Qdrant client from environment variables."""
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY")

    print(f"Connecting to Qdrant at {url}...")

    return QdrantClient(
        url=url,
        api_key=api_key,
        timeout=60,
    )


def collection_exists(client: QdrantClient, collection_name: str) -> bool:
    """Check if collection exists."""
    try:
        client.get_collection(collection_name)
        return True
    except (UnexpectedResponse, Exception):
        return False


def delete_collection(client: QdrantClient, collection_name: str) -> None:
    """Delete collection if exists."""
    if collection_exists(client, collection_name):
        print(f"Deleting existing collection: {collection_name}")
        client.delete_collection(collection_name)
        print(f"  Deleted: {collection_name}")


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
    """Create indexes on payload fields for fast filtering and deletion.

    Indexes match the payload contract in qdrant_writer.py:
    - file_id (flat): fast delete by file
    - metadata.file_id: filter by file in queries
    - metadata.source: filter by source path
    - metadata.file_name: filter by filename
    - metadata.mime_type: filter by document type
    """
    print("Creating payload indexes...")

    # Keyword indexes (exact match filtering + deletion)
    keyword_fields = [
        "file_id",  # Flat field for fast delete
        "metadata.file_id",  # Nested field for query filtering
        "metadata.doc_id",  # Small-to-big doc grouping
        "metadata.source",  # Source path filtering
        "metadata.file_name",  # Filename filtering
        "metadata.mime_type",  # Document type filtering
        "metadata.topic",  # Topic pre-filter routing
        "metadata.doc_type",  # Content-layer doc type filtering
    ]

    for field in keyword_fields:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
            print(f"  Created keyword index: {field}")
        except Exception as e:
            print(f"  Warning: Could not create index {field}: {e}")

    # Integer indexes for ordering/pagination
    integer_fields = [
        "metadata.order",  # Chunk ordering for small-to-big
        "metadata.chunk_id",  # Chunk position
    ]

    for field in integer_fields:
        try:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=PayloadSchemaType.INTEGER,
            )
            print(f"  Created integer index: {field}")
        except Exception as e:
            print(f"  Warning: Could not create index {field}: {e}")


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
