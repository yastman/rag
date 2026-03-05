#!/usr/bin/env python3
"""Ensure Qdrant payload indexes exist for all collections.

Creates missing keyword and integer payload indexes needed for efficient
filtering and order_by queries. Safe to run multiple times (idempotent).

Issue: #810 — VPS/local parity: Qdrant indexes

Usage:
    python scripts/qdrant_ensure_indexes.py
    python scripts/qdrant_ensure_indexes.py --collection gdrive_documents_bge
    QDRANT_URL=http://qdrant:6333 python scripts/qdrant_ensure_indexes.py
"""

import argparse
import os
import sys

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import PayloadSchemaType


KEYWORD_FIELDS = [
    "file_id",
    "metadata.file_id",
    "metadata.doc_id",
    "metadata.source",
    "metadata.file_name",
    "metadata.mime_type",
]

INTEGER_FIELDS = [
    "metadata.order",
    "metadata.chunk_id",
]


def get_qdrant_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY")
    return QdrantClient(url=url, api_key=api_key, timeout=30)


def ensure_indexes(client: QdrantClient, collection: str) -> None:
    """Create payload indexes for *collection* if they don't exist.

    Args:
        client: Connected Qdrant client.
        collection: Collection name to index.
    """
    for field in KEYWORD_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
            print(f"  OK: {field} (keyword)")
        except UnexpectedResponse as e:
            if "already exists" in str(e).lower() or e.status_code in (400, 409):
                print(f"  SKIP: {field} already indexed")
            else:
                print(f"  ERROR: {field}: {e}", file=sys.stderr)

    for field in INTEGER_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field,
                field_schema=PayloadSchemaType.INTEGER,
            )
            print(f"  OK: {field} (integer)")
        except UnexpectedResponse as e:
            if "already exists" in str(e).lower() or e.status_code in (400, 409):
                print(f"  SKIP: {field} already indexed")
            else:
                print(f"  ERROR: {field}: {e}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        default="gdrive_documents_bge",
        help="Qdrant collection name (default: gdrive_documents_bge)",
    )
    args = parser.parse_args()

    client = get_qdrant_client()
    print(f"Ensuring indexes for collection: {args.collection}")
    ensure_indexes(client, args.collection)
    print("Done.")


if __name__ == "__main__":
    main()
