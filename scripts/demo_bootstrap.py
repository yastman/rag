#!/usr/bin/env python3
"""Idempotent demo bootstrap for both product Qdrant collections (#3202).

One command prepares the configured knowledge collection and the ``apartments``
collection so the bot startup readiness gate (see ``src.runtime.qdrant.readiness``
and the bot preflight) can pass:

1. **Setup** — create a missing collection with the documented schema
   (dense@1024 + colbert + bm42 sparse, contract payload indexes). Existing
   collections are never dropped or rewritten: an incompatible schema is
   reported as a failure with rollback guidance instead.
2. **Ingest** — when a collection is empty, load the shipped demo data:
   ``data/test/sample_articles.json`` (knowledge corpus) and the shipped
   ``data/apartments.csv`` catalog (requires the BGE-M3 service). Populated
   collections are preserved untouched.
3. **Verify** — run the readiness contracts plus deterministic demo probes:
   every shipped apartment row must be reachable through the production filter
   path, the known-corpus question's source document must be present, and the
   intentional no-result probe must stay empty — proving advertised queries
   against the exact prepared data without needing the embedding service.

Usage:
    uv run python -m scripts.demo_bootstrap                  # setup + ingest + verify
    uv run python -m scripts.demo_bootstrap --verify-only    # read-only gate

Exit 0 = both collections ready; 1 = actionable failures (printed).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse

from scripts._qdrant_collection_setup import (
    APARTMENT_PAYLOAD_INDEX_FIELDS,
    GDRIVE_PAYLOAD_INDEX_FIELDS,
    create_payload_indexes,
)
from src.runtime.qdrant.readiness import (
    APARTMENTS_COLLECTION,
    KNOWLEDGE_DEMO_DOC_IDS,
    CollectionReadiness,
    apartment_demo_point_id,
    apartment_demo_probes,
    apartments_contract,
    knowledge_contract,
    knowledge_demo_point_id,
    knowledge_demo_probes,
    validate_collection,
)


KNOWLEDGE_DEMO_JSON = Path("data/test/sample_articles.json")
APARTMENTS_DEMO_CSV = Path("data/apartments.csv")
DEFAULT_QDRANT_URL = "http://localhost:6333"
DEFAULT_BGE_URL = "http://localhost:8000"


def resolve_knowledge_collection() -> str:
    """Resolve the knowledge collection name incl. quantization suffix."""
    from src.config.qdrant_policy import resolve_collection_name

    return resolve_collection_name(
        os.getenv("QDRANT_COLLECTION", "gdrive_documents_bge"),
        os.getenv("QDRANT_QUANTIZATION_MODE", "off"),
    )


# ---------------------------------------------------------------------------
# Schema setup (idempotent, non-destructive)
# ---------------------------------------------------------------------------


def create_knowledge_collection_schema(client: QdrantClient, collection_name: str) -> None:
    """Create the knowledge collection with the standard BGE-M3 schema."""
    from qdrant_client.models import (
        BinaryQuantization,
        BinaryQuantizationConfig,
        Distance,
        HnswConfigDiff,
        Modifier,
        MultiVectorComparator,
        MultiVectorConfig,
        OptimizersConfigDiff,
        SparseVectorParams,
        VectorParams,
    )

    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "dense": VectorParams(
                size=1024,
                distance=Distance.COSINE,
                hnsw_config=HnswConfigDiff(m=16, ef_construct=200, on_disk=False),
                quantization_config=BinaryQuantization(
                    binary=BinaryQuantizationConfig(always_ram=True)
                ),
                on_disk=True,
            ),
            "colbert": VectorParams(
                size=1024,
                distance=Distance.COSINE,
                multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                hnsw_config=HnswConfigDiff(m=0),
                on_disk=True,
            ),
        },
        sparse_vectors_config={
            "bm42": SparseVectorParams(modifier=Modifier.IDF),
        },
        optimizers_config=OptimizersConfigDiff(
            indexing_threshold=20000,
            memmap_threshold=50000,
        ),
    )
    create_payload_indexes(client, collection_name, GDRIVE_PAYLOAD_INDEX_FIELDS)
    print(f"  [OK] Created knowledge collection '{collection_name}' with contract schema")


def create_apartments_collection_schema(client: QdrantClient, collection_name: str) -> None:
    """Create the apartments collection; mirrors scripts/apartments/setup_collection.py."""
    from qdrant_client.models import (
        BinaryQuantization,
        BinaryQuantizationConfig,
        Distance,
        HnswConfigDiff,
        Modifier,
        MultiVectorComparator,
        MultiVectorConfig,
        SparseVectorParams,
        VectorParams,
    )

    client.create_collection(
        collection_name=collection_name,
        vectors_config={
            "dense": VectorParams(
                size=1024,
                distance=Distance.COSINE,
                hnsw_config=HnswConfigDiff(m=16, ef_construct=200, on_disk=False),
                quantization_config=BinaryQuantization(
                    binary=BinaryQuantizationConfig(always_ram=True)
                ),
                on_disk=True,
            ),
            "colbert": VectorParams(
                size=1024,
                distance=Distance.COSINE,
                multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                hnsw_config=HnswConfigDiff(m=0),
                on_disk=True,
            ),
        },
        sparse_vectors_config={
            "bm42": SparseVectorParams(modifier=Modifier.IDF),
        },
    )
    create_payload_indexes(client, collection_name, APARTMENT_PAYLOAD_INDEX_FIELDS)
    print(f"  [OK] Created apartments collection '{collection_name}' with contract schema")


# ---------------------------------------------------------------------------
# Demo data ingest (only ever runs against an EMPTY collection)
# ---------------------------------------------------------------------------


def ingest_knowledge_demo(
    client: QdrantClient,
    collection_name: str,
    json_path: Path,
    bge_url: str,
) -> int:
    """Embed and upsert the shipped demo knowledge corpus. Returns point count."""
    from qdrant_client.models import PointStruct, SparseVector

    from src.services.bge_m3_client import BGEM3SyncClient

    documents = json.loads(json_path.read_text(encoding="utf-8"))["documents"]
    if not documents:
        raise ValueError(f"demo knowledge corpus is empty: {json_path}")

    texts = [doc["content"] for doc in documents]
    bge = BGEM3SyncClient(base_url=bge_url)
    try:
        hybrid = bge.encode_hybrid(texts)
    finally:
        bge.close()

    colbert_vecs = hybrid.colbert_vecs or []
    points: list[PointStruct] = []
    for doc, dense, sparse in zip(
        documents, hybrid.dense_vecs, hybrid.lexical_weights, strict=True
    ):
        vector: dict[str, Any] = {
            "dense": dense,
            "bm42": SparseVector(indices=sparse["indices"], values=sparse["values"]),
        }
        if colbert_vecs:
            vector["colbert"] = colbert_vecs[len(points)]
        points.append(
            PointStruct(
                id=knowledge_demo_point_id(doc["id"]),
                vector=vector,
                payload={
                    "page_content": doc["content"],
                    "metadata": {
                        "id": doc["id"],
                        "title": doc["title"],
                        **doc.get("metadata", {}),
                    },
                },
            )
        )

    client.upsert(collection_name=collection_name, points=points, wait=True)
    print(
        f"  [OK] Ingested {len(points)} shipped demo documents into "
        f"'{collection_name}' from {json_path}"
    )
    return len(points)


def ingest_apartments_demo(csv_path: str, qdrant_url: str, bge_url: str, state_path: str) -> dict:
    """Ingest the shipped apartments CSV via the incremental runner."""
    from src.ingestion.apartments.runner import IncrementalApartmentIngester

    ingester = IncrementalApartmentIngester(
        csv_path=csv_path,
        qdrant_url=qdrant_url,
        bge_url=bge_url,
        state_path=state_path,
    )
    return ingester.run_incremental(force_full=True)


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def _shipped_apartment_rows(csv_path: str) -> list[dict[str, Any]]:
    """Read the shipped CSV into the minimal dict shape the probes need."""
    from src.ingestion.apartments.source import read_apartments_csv

    return [
        {
            "complex_name": rec.complex_name,
            "section": rec.section,
            "apartment_number": rec.apartment_number,
            "rooms": rec.rooms,
            "city": rec.city,
        }
        for _key, _change, rec in read_apartments_csv(csv_path)
    ]


async def _shipped_ids_present(async_client: Any, collection: str, point_ids: list[str]) -> bool:
    """Exact-count check that every deterministic demo point id is present."""
    from uuid import UUID

    from qdrant_client.models import Filter, HasIdCondition

    ids: list[int | str | UUID] = list(point_ids)
    count = await async_client.count(
        collection_name=collection,
        count_filter=Filter(must=[HasIdCondition(has_id=ids)]),
        exact=True,
    )
    return int(count.count) == len(point_ids)


async def verify_ready(args: argparse.Namespace) -> list[CollectionReadiness]:
    """Run readiness contracts (and eligible demo probes) for both collections.

    Demo probes are enforced only against the data this repo ships: when a
    populated environment no longer contains the shipped demo points, the
    shipped-data probes are skipped (environment preserved) and only the
    intentional no-result probe still runs — a legitimate no-result search
    must stay distinguishable from missing/empty data everywhere.
    """
    from qdrant_client import AsyncQdrantClient

    knowledge = knowledge_contract(args.knowledge_collection)
    apartments = apartments_contract().with_collection_name(args.apartments_collection)

    async_client = AsyncQdrantClient(url=args.qdrant_url, api_key=args.qdrant_api_key)
    try:
        readiness: list[CollectionReadiness] = [
            await validate_collection(async_client, knowledge),
            await validate_collection(async_client, apartments),
        ]
        knowledge_readiness, apartments_readiness = readiness

        if knowledge_readiness.ok:
            corpus_ids = [knowledge_demo_point_id(doc_id) for doc_id in KNOWLEDGE_DEMO_DOC_IDS]
            if await _shipped_ids_present(async_client, args.knowledge_collection, corpus_ids):
                readiness[0] = await validate_collection(
                    async_client,
                    knowledge,
                    run_probes=True,
                    probes=knowledge_demo_probes(),
                )
            else:
                print(
                    f"  [SKIP] Shipped demo corpus not detected in "
                    f"'{args.knowledge_collection}' — populated environment "
                    "preserved; corpus probes not enforced"
                )

        if apartments_readiness.ok:
            rows = _shipped_apartment_rows(args.apartments_csv)
            shipped_ids = [
                apartment_demo_point_id(r["complex_name"], r["section"], r["apartment_number"])
                for r in rows
            ]
            if await _shipped_ids_present(async_client, args.apartments_collection, shipped_ids):
                readiness[1] = await validate_collection(
                    async_client,
                    apartments,
                    run_probes=True,
                    probes=apartment_demo_probes(rows),
                )
            else:
                print(
                    f"  [SKIP] Shipped demo rows not detected in "
                    f"'{args.apartments_collection}' — populated environment "
                    "preserved; shipped-row probes not enforced"
                )
                no_result_probe = apartment_demo_probes(rows)[-1:]
                readiness[1] = await validate_collection(
                    async_client,
                    apartments,
                    run_probes=True,
                    probes=no_result_probe,
                )
    finally:
        await async_client.close()

    return readiness


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _collection_info(client: QdrantClient, collection: str) -> Any:
    try:
        return client.get_collection(collection)
    except (UnexpectedResponse, Exception):
        return None


def _schema_compatible(info: Any) -> bool:
    """Coarse schema sniff so ingest never writes into an incompatible collection.

    Full dimension/index validation happens in the readiness verification; this
    only gates the *ingest* step (required vector names must exist).
    """
    from src.runtime.qdrant.readiness import _dense_vector_names, _sparse_vector_names

    dense = _dense_vector_names(info)
    sparse = _sparse_vector_names(info)
    return "dense" in dense and "bm42" in sparse


def _schema_failure(collection: str) -> str:
    return (
        f"[schema_incompatible] collection '{collection}' does not match the "
        "contract — left untouched (non-destructive); see "
        "docs/LOCAL-DEVELOPMENT.md (Demo data readiness) for rollback and migration"
    )


def _state_path(args: argparse.Namespace) -> str:
    """Runner state file keyed by collection so overrides never collide."""
    return f".apartments_ingestion_state_{args.apartments_collection}.json"


def _bootstrap_knowledge(
    client: QdrantClient, args: argparse.Namespace, failures: list[str]
) -> None:
    info = _collection_info(client, args.knowledge_collection)
    if info is None:
        create_knowledge_collection_schema(client, args.knowledge_collection)
        info = _collection_info(client, args.knowledge_collection)
    elif not _schema_compatible(info):
        failures.append(_schema_failure(args.knowledge_collection))
        return
    if int(getattr(info, "points_count", 0) or 0) == 0:
        print(f"  [..] Knowledge collection '{args.knowledge_collection}' is empty; ingesting")
        try:
            ingest_knowledge_demo(
                client, args.knowledge_collection, Path(args.knowledge_json), args.bge_url
            )
        except Exception as exc:
            failures.append(
                f"[ingest_failed] knowledge demo ingest failed: {exc} — start the "
                f"BGE-M3 service at {args.bge_url} and re-run (schema is already ready)"
            )
    else:
        print(
            f"  [OK] Knowledge collection '{args.knowledge_collection}' already "
            f"populated ({info.points_count} points) — preserved"
        )


def _bootstrap_apartments(
    client: QdrantClient, args: argparse.Namespace, failures: list[str]
) -> None:
    info = _collection_info(client, args.apartments_collection)
    if info is None:
        create_apartments_collection_schema(client, args.apartments_collection)
        info = _collection_info(client, args.apartments_collection)
    elif not _schema_compatible(info):
        failures.append(_schema_failure(args.apartments_collection))
        return
    if int(getattr(info, "points_count", 0) or 0) == 0:
        print(f"  [..] Apartments collection '{args.apartments_collection}' is empty; ingesting")
        try:
            stats = ingest_apartments_demo(
                args.apartments_csv, args.qdrant_url, args.bge_url, _state_path(args)
            )
            print(f"  [OK] Apartments ingest stats: {stats}")
        except Exception as exc:
            failures.append(
                f"[ingest_failed] apartments demo ingest failed: {exc} — start the "
                f"BGE-M3 service at {args.bge_url} and re-run (schema is already ready)"
            )
    else:
        print(
            f"  [OK] Apartments collection '{args.apartments_collection}' already "
            f"populated ({info.points_count} points) — preserved"
        )


def main(argv: list[str] | None = None) -> int:
    """Prepare and verify both product collections. Exit 0 = ready."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Read-only readiness verification; no schema or data changes",
    )
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY"))
    parser.add_argument("--knowledge-collection", default=None)
    parser.add_argument("--apartments-collection", default=APARTMENTS_COLLECTION)
    parser.add_argument("--apartments-csv", default=str(APARTMENTS_DEMO_CSV))
    parser.add_argument("--knowledge-json", default=str(KNOWLEDGE_DEMO_JSON))
    parser.add_argument("--bge-url", default=os.getenv("BGE_M3_URL", DEFAULT_BGE_URL))
    args = parser.parse_args(argv)
    if args.knowledge_collection is None:
        args.knowledge_collection = resolve_knowledge_collection()

    print("=== Demo bootstrap: Qdrant product collections (#3202) ===")
    print(f"  knowledge:  {args.knowledge_collection}")
    print(f"  apartments: {args.apartments_collection}")

    failures: list[str] = []

    if not args.verify_only:
        client = QdrantClient(url=args.qdrant_url, api_key=args.qdrant_api_key, timeout=60)
        try:
            client.get_collections()
        except Exception as exc:
            print(f"  [FAIL] Cannot reach Qdrant at {args.qdrant_url}: {exc}")
            return 1

        _bootstrap_knowledge(client, args, failures)
        _bootstrap_apartments(client, args, failures)
        client.close()

    readiness = asyncio.run(verify_ready(args))
    print("\n=== Readiness verification ===")
    for item in readiness:
        label = f"{item.role}/{item.collection}"
        if item.ok:
            probes_note = f" (probes: {item.probe_results})" if item.probe_results else ""
            print(f"  [OK] {label}: {item.points_count} points{probes_note}")
        else:
            failures.extend(f.render() for f in item.failures)

    if failures:
        print("\nDemo bootstrap FAILED — actionable errors:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nDemo bootstrap PASSED: both product collections are ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
