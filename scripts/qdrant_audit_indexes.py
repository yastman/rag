#!/usr/bin/env python3
"""Audit Qdrant payload indexes against the expected contract.

Expected fields are derived from src/ingestion/unified/cli.py bootstrap and
src/runtime/services/qdrant.py _build_filter (which prefixes filter keys with
metadata.*).

Exit 0 = PASS, Exit 1 = FAIL (missing indexes).
"""

import json
import os
import sys
import urllib.request


QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
COLLECTION = os.environ.get("QDRANT_COLLECTION", "gdrive_documents_bge")

# Fields actually used in runtime filter queries (from _retrieve.py + qdrant.py)
# plus ingestion-critical fields used for orphan cleanup and lookup.
EXPECTED_INDEXES = {
    "file_id",
    "metadata.file_id",
    "metadata.doc_id",
    "metadata.source",
    "metadata.file_name",
    "metadata.mime_type",
    "metadata.source_type",
    "metadata.topic",  # runtime filter: _compute_retrieval_filters
    "metadata.doc_type",  # runtime filter: prefer_faq_doc_type
    "metadata.jurisdiction",
    "metadata.audience",
    "metadata.language",
    "metadata.order",
    "metadata.chunk_id",
}


def main() -> int:
    url = f"{QDRANT_URL}/collections/{COLLECTION}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as exc:
        print(f"FAIL: could not reach Qdrant at {url}: {exc}", file=sys.stderr)
        return 1

    payload_schema: dict = data.get("result", {}).get("payload_schema") or {}
    indexed_fields = set(payload_schema.keys())

    missing = EXPECTED_INDEXES - indexed_fields
    if missing:
        print(f"FAIL: {len(missing)} missing payload index(es) in '{COLLECTION}':")
        for field in sorted(missing):
            print(f"  - {field}")
        return 1

    print(f"PASS: all {len(EXPECTED_INDEXES)} expected payload indexes present in '{COLLECTION}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
