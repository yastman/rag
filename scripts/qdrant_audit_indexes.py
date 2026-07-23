#!/usr/bin/env python3
"""Audit Qdrant payload indexes against the configured collection contract.

Exit 0 = PASS, Exit 1 = FAIL (missing indexes).
"""

import os
import sys


try:
    from scripts._qdrant_collection_setup import (
        PAYLOAD_INDEX_FIELDS_BY_COLLECTION,
        get_qdrant_client,
        payload_index_types,
    )
    from scripts.setup_binary_collection import PAYLOAD_INDEX_FIELDS
except ModuleNotFoundError:
    from _qdrant_collection_setup import (
        PAYLOAD_INDEX_FIELDS_BY_COLLECTION,
        get_qdrant_client,
        payload_index_types,
    )
    from setup_binary_collection import PAYLOAD_INDEX_FIELDS


QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "gdrive_documents_bge")


def expected_indexes(collection: str) -> set[str]:
    """Return the payload-index names required by one configured collection."""
    field_map = (
        PAYLOAD_INDEX_FIELDS
        if collection.endswith("_binary")
        else PAYLOAD_INDEX_FIELDS_BY_COLLECTION[collection]
    )
    return set(payload_index_types(field_map))


EXPECTED_INDEXES = expected_indexes(COLLECTION)


def schema_type(schema: object) -> str | None:
    """Return an SDK payload schema's declared data type, when available."""
    data_type = getattr(schema, "data_type", None)
    if data_type is None and isinstance(schema, dict):
        data_type = schema.get("data_type")
    return getattr(data_type, "value", data_type)


def main() -> int:
    try:
        expected = expected_indexes(COLLECTION)
    except KeyError:
        print(f"FAIL: no payload-index contract for collection '{COLLECTION}'", file=sys.stderr)
        return 1
    try:
        payload_schema = (
            get_qdrant_client(timeout=10, announce=False).get_collection(COLLECTION).payload_schema
            or {}
        )
    except Exception as exc:
        print(
            f"FAIL: could not reach Qdrant at {QDRANT_URL}/collections/{COLLECTION}: {exc}",
            file=sys.stderr,
        )
        return 1
    indexed_fields = set(payload_schema)
    wrong_types = {
        field: expected_type
        for field, expected_type in payload_index_types(
            PAYLOAD_INDEX_FIELDS
            if COLLECTION.endswith("_binary")
            else PAYLOAD_INDEX_FIELDS_BY_COLLECTION[COLLECTION]
        ).items()
        if field in payload_schema
        and (actual_type := schema_type(payload_schema[field])) is not None
        and actual_type != expected_type
    }

    missing = expected - indexed_fields
    if missing:
        print(f"FAIL: {len(missing)} missing payload index(es) in '{COLLECTION}':")
        for field in sorted(missing):
            print(f"  - {field}")
        return 1
    if wrong_types:
        print(f"FAIL: {len(wrong_types)} payload index(es) have the wrong type in '{COLLECTION}':")
        for field, expected_type in sorted(wrong_types.items()):
            print(
                f"  - {field}: expected {expected_type}, got {schema_type(payload_schema[field])}"
            )
        return 1

    print(f"PASS: all {len(expected)} expected payload indexes present in '{COLLECTION}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
