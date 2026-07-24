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
import sys

from qdrant_client import QdrantClient


try:
    from scripts._qdrant_collection_setup import (
        GDRIVE_PAYLOAD_INDEX_FIELDS,
        create_payload_indexes,
    )
    from scripts._qdrant_collection_setup import (
        get_qdrant_client as _get_qdrant_client,
    )
except ModuleNotFoundError:
    from _qdrant_collection_setup import (
        GDRIVE_PAYLOAD_INDEX_FIELDS,
        create_payload_indexes,
    )
    from _qdrant_collection_setup import (
        get_qdrant_client as _get_qdrant_client,
    )


PAYLOAD_INDEX_FIELDS = GDRIVE_PAYLOAD_INDEX_FIELDS


def get_qdrant_client() -> QdrantClient:
    """Create the short-timeout Qdrant client used by this maintenance script."""
    return _get_qdrant_client(timeout=30, announce=False)


def ensure_indexes(client: QdrantClient, collection: str) -> None:
    """Create payload indexes for *collection* if they don't exist.

    Args:
        client: Connected Qdrant client.
        collection: Collection name to index.
    """
    create_payload_indexes(client, collection, PAYLOAD_INDEX_FIELDS)


def main(argv: list[str] | None = None) -> int:
    """Ensure configured payload indexes exist."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        default="gdrive_documents_bge",
        help="Qdrant collection name (default: gdrive_documents_bge)",
    )
    args = parser.parse_args(argv)

    try:
        client = get_qdrant_client()
        print(f"Ensuring indexes for collection: {args.collection}")
        ensure_indexes(client, args.collection)
    except Exception as error:
        print(f"FAIL: could not ensure indexes for '{args.collection}': {error}", file=sys.stderr)
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
