#!/usr/bin/env python3
"""Index services.yaml content into Qdrant via BGE-M3 embeddings.

Idempotent: uses deterministic point IDs (uuid5) — re-running updates, not duplicates.
One chunk per service (card_text field).

Usage:
    uv run python scripts/index_services.py
    uv run python scripts/index_services.py --services-yaml telegram_bot/config/services.yaml
    uv run python scripts/index_services.py --dry-run
"""

from __future__ import annotations

import argparse
import functools
import os
import sys
import uuid
from pathlib import Path

import yaml
from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    SparseVector,
)


print = functools.partial(print, flush=True)  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_SERVICES_YAML = "telegram_bot/config/services.yaml"
DEFAULT_COLLECTION = "gdrive_documents_bge"
DEFAULT_BGE_M3_URL = "http://localhost:8000"
DEFAULT_QDRANT_URL = "http://localhost:6333"
EMBED_BATCH_SIZE = 8
UPLOAD_BATCH_SIZE = 10
UPLOAD_MAX_RETRIES = 3

DOC_ID = "services.yaml"
SOURCE = "services.yaml"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_services_yaml(path: Path | str) -> list[dict]:
    """Parse services.yaml and return services that have card_text.

    Args:
        path: Path to services.yaml file.

    Returns:
        List of dicts with keys: service_key, title, card_text, emoji.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"services.yaml not found: {path}")

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    services_map: dict = raw.get("services", {}) or {}

    result = []
    for key, cfg in services_map.items():
        if not isinstance(cfg, dict):
            continue
        card_text = cfg.get("card_text", "")
        if not card_text or not card_text.strip():
            continue
        result.append(
            {
                "service_key": key,
                "title": cfg.get("title", key),
                "emoji": cfg.get("emoji", ""),
                "card_text": card_text,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def build_chunks(services: list[dict]) -> list[dict]:
    """Build one chunk per service with deterministic IDs.

    Args:
        services: List returned by parse_services_yaml().

    Returns:
        List of chunk dicts ready for embedding.
    """
    chunks = []
    for svc in services:
        service_key = svc["service_key"]
        # Deterministic ID: same key → same UUID across runs (idempotency)
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"services::{service_key}"))
        chunks.append(
            {
                "id": point_id,
                "text": svc["card_text"],
                "service_key": service_key,
                "title": svc["title"],
                "emoji": svc["emoji"],
                "source": SOURCE,
                "doc_id": DOC_ID,
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# PointStruct construction
# ---------------------------------------------------------------------------


def build_points(chunks: list[dict], embeddings: dict[str, list]) -> list[PointStruct]:
    """Assemble Qdrant PointStruct list from chunks and embeddings.

    Args:
        chunks: List from build_chunks().
        embeddings: Dict with keys "dense", "sparse", "colbert".

    Returns:
        List of PointStruct ready for upload_points().
    """
    points = []
    for i, chunk in enumerate(chunks):
        sparse_data = embeddings["sparse"][i]
        points.append(
            PointStruct(
                id=chunk["id"],
                vector={
                    "dense": embeddings["dense"][i],
                    "colbert": embeddings["colbert"][i],
                    "bm42": SparseVector(
                        indices=sparse_data["indices"],
                        values=sparse_data["values"],
                    ),
                },
                payload={
                    "page_content": chunk["text"],
                    "text": chunk["text"],
                    "metadata": {
                        "source": SOURCE,
                        "doc_id": chunk["doc_id"],
                        "file_name": SOURCE,
                        "service_key": chunk["service_key"],
                        "title": chunk["title"],
                    },
                },
            )
        )
    return points


# ---------------------------------------------------------------------------
# BGE-M3 helpers (same pattern as index_local_docs.py)
# ---------------------------------------------------------------------------


def _create_bge_client(bge_url: str):
    """Create BGEM3SyncClient from project SDK."""
    try:
        from telegram_bot.services.bge_m3_client import (
            BGEM3SyncClient,  # type: ignore[import-not-found]
        )

        return BGEM3SyncClient(base_url=bge_url)
    except ImportError:
        return None


def encode_hybrid_sdk(client: object, texts: list[str]) -> dict[str, list]:
    """Encode via BGEM3SyncClient.encode_hybrid()."""
    result = client.encode_hybrid(texts)  # type: ignore[union-attr]
    return {
        "dense": result.dense_vecs,
        "sparse": result.lexical_weights,
        "colbert": result.colbert_vecs,
    }


def encode_hybrid_http(
    texts: list[str],
    bge_url: str,
    batch_size: int = EMBED_BATCH_SIZE,
) -> dict[str, list]:
    """Fallback: encode via raw HTTP to /encode/hybrid."""
    import httpx

    dense: list = []
    sparse: list = []
    colbert: list = []
    total = len(texts)
    for start in range(0, total, batch_size):
        batch = texts[start : start + batch_size]
        n = start + len(batch)
        print(f"  hybrid [{n}/{total}]...")
        resp = httpx.post(
            f"{bge_url}/encode/hybrid",
            json={"texts": batch},
            timeout=600.0,
        )
        resp.raise_for_status()
        data = resp.json()
        dense.extend(data["dense_vecs"])
        sparse.extend(data["lexical_weights"])
        colbert.extend(data["colbert_vecs"])
    return {"dense": dense, "sparse": sparse, "colbert": colbert}


def encode_texts(
    texts: list[str],
    bge_url: str,
    batch_size: int = EMBED_BATCH_SIZE,
) -> dict[str, list]:
    """Encode texts — try SDK first, fall back to HTTP."""
    client = _create_bge_client(bge_url)
    if client is not None:
        print("  Using BGEM3SyncClient SDK")
        return encode_hybrid_sdk(client, texts)
    print("  SDK unavailable, using HTTP fallback")
    return encode_hybrid_http(texts, bge_url, batch_size)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Index services.yaml into Qdrant")
    parser.add_argument(
        "--services-yaml",
        default=os.getenv("SERVICES_YAML", DEFAULT_SERVICES_YAML),
        help="Path to services.yaml (default: telegram_bot/config/services.yaml)",
    )
    parser.add_argument("--collection", "-c", default=DEFAULT_COLLECTION)
    parser.add_argument("--bge-url", default=os.getenv("BGE_M3_URL", DEFAULT_BGE_M3_URL))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL))
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse + embed but skip Qdrant upsert",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Services Indexer (BGE-M3 → Qdrant)")
    print("=" * 60)
    print(f"  YAML:       {args.services_yaml}")
    print(f"  Collection: {args.collection}")
    print(f"  BGE-M3:     {args.bge_url}")
    print(f"  Qdrant:     {args.qdrant_url}")
    print(f"  Dry run:    {args.dry_run}")
    print()

    # 1. Parse
    yaml_path = Path(args.services_yaml)
    try:
        services = parse_services_yaml(yaml_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    if not services:
        print("No services with card_text found — nothing to index.")
        return 0

    print(f"Found {len(services)} services with card_text:")
    for svc in services:
        print(f"  • {svc['service_key']}: {svc['title']}")
    print()

    # 2. Build chunks
    chunks = build_chunks(services)
    texts = [c["text"] for c in chunks]

    # 3. Qdrant preflight (skip in dry-run)
    qdrant: QdrantClient | None = None
    if not args.dry_run:
        qdrant = QdrantClient(url=args.qdrant_url, timeout=60)
        if not qdrant.collection_exists(args.collection):
            print(f"ERROR: Collection '{args.collection}' does not exist.", file=sys.stderr)
            print("Run: make ingest-setup", file=sys.stderr)
            return 1

    # 4. Embed
    print("Embedding...")
    embeddings = encode_texts(texts, args.bge_url)
    print(f"  Embedded {len(chunks)} chunks\n")

    # 5. Build points
    points = build_points(chunks, embeddings)

    if args.dry_run:
        print(f"[dry-run] Would upsert {len(points)} points to '{args.collection}'")
        for p in points:
            print(f"  id={p.id}  key={p.payload['metadata']['service_key']}")  # type: ignore[index]
        return 0

    # 6. Upsert (idempotent — same IDs overwrite existing points)
    assert qdrant is not None
    print(f"Upserting {len(points)} points → '{args.collection}'...")
    qdrant.upload_points(
        collection_name=args.collection,
        points=iter(points),
        batch_size=UPLOAD_BATCH_SIZE,
        max_retries=UPLOAD_MAX_RETRIES,
        wait=True,
    )
    print(f"✓ Done — {len(points)} services indexed into '{args.collection}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
