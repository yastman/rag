#!/usr/bin/env python3
"""Setup Qdrant collection and payload indexes for document ingestion pipeline.

Creates a 'documents' collection optimized for the ingestion pipeline with:
- Dense vectors (1024-dim, Voyage voyage-3-large)
- Payload indexes for file_id, folder_id, mime_type (fast filtering/deletion)

Milestone J: Document Ingestion Pipeline (2026-02-02)

Usage:
    python scripts/setup_ingestion_collection.py
    python scripts/setup_ingestion_collection.py --force  # Recreate if exists
    python scripts/setup_ingestion_collection.py --collection my_docs
"""

import argparse
import os
import sys

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    VectorParams,
)


COLLECTION_NAME = "documents"
VECTOR_SIZE = 1024  # Voyage voyage-3-large / voyage-4-large


def get_client() -> QdrantClient:
    """Create Qdrant client from environment."""
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY")

    return QdrantClient(url=url, api_key=api_key, timeout=60)


def collection_exists(client: QdrantClient, name: str) -> bool:
    """Check if collection exists."""
    try:
        client.get_collection(name)
        return True
    except (UnexpectedResponse, Exception):
        return False


def setup_collection(client: QdrantClient, name: str = COLLECTION_NAME, force: bool = False):
    """Create collection with proper indexes."""
    # Check/delete existing
    if collection_exists(client, name):
        if force:
            print(f"Deleting existing collection: {name}")
            client.delete_collection(name)
        else:
            print(f"Collection exists: {name}")
            print("Use --force to recreate.")
            return

    # Create collection
    print(f"Creating collection: {name}")
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )
    print(f"  Created collection: {name} ({VECTOR_SIZE}-dim, cosine)")

    # Create payload indexes for fast filtering/deletion
    indexes = [
        ("file_id", PayloadSchemaType.KEYWORD),
        ("folder_id", PayloadSchemaType.KEYWORD),
        ("mime_type", PayloadSchemaType.KEYWORD),
        ("file_name", PayloadSchemaType.KEYWORD),
    ]

    print("Creating payload indexes...")
    for field_name, field_type in indexes:
        try:
            client.create_payload_index(
                collection_name=name,
                field_name=field_name,
                field_schema=field_type,
            )
            print(f"  Created index: {field_name} ({field_type})")
        except Exception as e:
            if "already exists" in str(e).lower():
                print(f"  Index exists: {field_name}")
            else:
                print(f"  Warning: {field_name}: {e}")

    # Print collection info
    info = client.get_collection(name)
    print("\nCollection ready:")
    print(f"  Name: {name}")
    print(f"  Points: {info.points_count}")
    print(f"  Status: {info.status}")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Setup Qdrant collection for ingestion pipeline",
    )
    parser.add_argument(
        "--collection",
        "-c",
        default=COLLECTION_NAME,
        help=f"Collection name (default: {COLLECTION_NAME})",
    )
    parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force recreation of collection",
    )

    args = parser.parse_args()

    try:
        client = get_client()
        setup_collection(client, args.collection, args.force)
        print("\nDone!")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
