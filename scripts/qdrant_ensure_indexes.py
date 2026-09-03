#!/usr/bin/env python3
"""Ensure Qdrant payload indexes exist for all product collections.

Creates missing keyword/integer/float/bool payload indexes needed for
efficient filtering and order_by queries. Safe to run multiple times
(idempotent, non-destructive: it only creates missing indexes and never
touches data or existing indexes).

Runs role-aware across BOTH product collections (#3202): the configured
knowledge collection (knowledge index contract) and the hard-coded
`apartments` collection (apartments index contract).

Issue: #810 — VPS/local parity: Qdrant indexes
       #3202 — readiness remediation path for both collections

Usage:
    python -m scripts.qdrant_ensure_indexes
    python -m scripts.qdrant_ensure_indexes --collection gdrive_documents_bge
    python -m scripts.qdrant_ensure_indexes --only apartments
    QDRANT_URL=http://qdrant:6333 python -m scripts.qdrant_ensure_indexes
"""

import argparse
import os
import sys
from typing import TYPE_CHECKING

from qdrant_client import QdrantClient


# Dual-mode imports (#3249): package import for `import scripts.<module>`, direct-script
# fallback for `python scripts/<file>.py`. The TYPE_CHECKING branch keeps a single
# binding so MyPy sees one definition while both invocation modes stay supported.
if TYPE_CHECKING:
    from scripts._qdrant_collection_setup import (
        APARTMENT_PAYLOAD_INDEX_FIELDS,
        GDRIVE_PAYLOAD_INDEX_FIELDS,
        create_payload_indexes,
    )
    from scripts._qdrant_collection_setup import (
        get_qdrant_client as _get_qdrant_client,
    )
else:
    try:
        from scripts._qdrant_collection_setup import (
            APARTMENT_PAYLOAD_INDEX_FIELDS,
            GDRIVE_PAYLOAD_INDEX_FIELDS,
            create_payload_indexes,
        )
        from scripts._qdrant_collection_setup import (
            get_qdrant_client as _get_qdrant_client,
        )
    except ModuleNotFoundError:
        from _qdrant_collection_setup import (
            APARTMENT_PAYLOAD_INDEX_FIELDS,
            GDRIVE_PAYLOAD_INDEX_FIELDS,
            create_payload_indexes,
        )
        from _qdrant_collection_setup import (
            get_qdrant_client as _get_qdrant_client,
        )


PAYLOAD_INDEX_FIELDS = GDRIVE_PAYLOAD_INDEX_FIELDS
DEFAULT_APARTMENTS_COLLECTION = "apartments"


def get_qdrant_client() -> QdrantClient:
    """Create the short-timeout Qdrant client used by this maintenance script."""
    return _get_qdrant_client(timeout=30, announce=False)


def ensure_indexes(
    client: QdrantClient,
    collection: str,
    field_map: tuple | None = None,
) -> None:
    """Create payload indexes for *collection* if they don't exist.

    Args:
        client: Connected Qdrant client.
        collection: Collection name to index.
        field_map: Index contract to apply; defaults to the knowledge
            (GDRIVE) contract for backwards compatibility.
    """
    create_payload_indexes(client, collection, field_map or PAYLOAD_INDEX_FIELDS)


def ensure_knowledge_indexes(client: QdrantClient, collection: str) -> None:
    """Ensure the knowledge collection's payload-index contract."""
    ensure_indexes(client, collection, GDRIVE_PAYLOAD_INDEX_FIELDS)


def ensure_apartments_indexes(client: QdrantClient, collection: str) -> None:
    """Ensure the apartments collection's payload-index contract."""
    ensure_indexes(client, collection, APARTMENT_PAYLOAD_INDEX_FIELDS)


def main(argv: list[str] | None = None) -> int:
    """Ensure contract payload indexes exist for both product collections."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--collection",
        default=os.getenv("QDRANT_COLLECTION", "gdrive_documents_bge"),
        help="Knowledge collection name (default: $QDRANT_COLLECTION or gdrive_documents_bge)",
    )
    parser.add_argument(
        "--apartments-collection",
        default=DEFAULT_APARTMENTS_COLLECTION,
        help="Apartments collection name (default: apartments)",
    )
    parser.add_argument(
        "--only",
        choices=("knowledge", "apartments"),
        default=None,
        help="Restrict the run to a single collection role",
    )
    args = parser.parse_args(argv)

    client: QdrantClient | None = None
    try:
        client = get_qdrant_client()
        targets: list[tuple[str, str]] = []
        if args.only in (None, "knowledge"):
            targets.append(("knowledge", args.collection))
        if args.only in (None, "apartments"):
            targets.append(("apartments", args.apartments_collection))

        for role, collection in targets:
            print(f"Ensuring {role} indexes for collection: {collection}")
            if role == "knowledge":
                ensure_knowledge_indexes(client, collection)
            else:
                ensure_apartments_indexes(client, collection)
    except Exception as error:
        print(f"FAIL: could not ensure indexes: {error}", file=sys.stderr)
        return 1

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
