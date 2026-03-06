#!/usr/bin/env python3
"""Index local Markdown files into Qdrant via BGE-M3 embeddings.

Document-scoped pipeline: for each file, chunk -> embed -> delete old -> upsert.
Idempotent: safe to re-run (deletes stale chunks by doc_id before inserting).

Usage:
    uv run python scripts/index_local_docs.py
    uv run python scripts/index_local_docs.py --docs-dir /path/to/docs
"""

from __future__ import annotations

import argparse
import functools
import os
import re
import sys
import uuid
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    SparseVector,
)


print = functools.partial(print, flush=True)  # type: ignore[assignment]

# --- Config defaults ---
DEFAULT_DOCS_DIR = "/home/user/drive-sync/Test"
DEFAULT_COLLECTION = "gdrive_documents_bge"
DEFAULT_BGE_M3_URL = "http://localhost:8000"
DEFAULT_QDRANT_URL = "http://localhost:6333"
MAX_CHUNK_CHARS = 2000  # ~500 tokens
EMBED_BATCH_SIZE = 4
UPLOAD_BATCH_SIZE = 1
UPLOAD_MAX_RETRIES = 3
PAYLOAD_INDEX_FIELDS = [
    "metadata.source",
    "metadata.doc_id",
    "metadata.file_name",
]


# --- Chunking ---


def _heading_level(line: str) -> int | None:
    m = re.match(r"^(#{1,3})\s", line)
    return len(m.group(1)) if m else None


def chunk_markdown(text: str, source_file: str) -> list[dict]:
    """Split markdown by ## headings, merge small sections."""
    lines = text.split("\n")
    sections: list[dict] = []
    current_heading = Path(source_file).stem
    current_lines: list[str] = []

    def _flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append({"heading": current_heading, "text": body})

    for line in lines:
        level = _heading_level(line)
        if level is not None and level <= 2:
            _flush()
            current_heading = line.lstrip("#").strip() or current_heading
            current_lines = []
        else:
            current_lines.append(line)
    _flush()

    # Split oversized sections by paragraphs
    chunks: list[dict] = []
    for sec in sections:
        txt = sec["text"]
        if len(txt) <= MAX_CHUNK_CHARS:
            chunks.append(sec)
        else:
            paragraphs = re.split(r"\n{2,}", txt)
            buf = ""
            for para in paragraphs:
                if buf and len(buf) + len(para) > MAX_CHUNK_CHARS:
                    chunks.append({"heading": sec["heading"], "text": buf.strip()})
                    buf = ""
                buf += para + "\n\n"
            if buf.strip():
                chunks.append({"heading": sec["heading"], "text": buf.strip()})

    return chunks


def load_document_chunks(md_file: Path) -> list[dict]:
    """Load and chunk a single .md file."""
    text = md_file.read_text(encoding="utf-8")
    file_chunks = chunk_markdown(text, md_file.name)
    doc_id = md_file.name
    for i, chunk in enumerate(file_chunks):
        chunk["source_file"] = md_file.name
        chunk["doc_id"] = doc_id
        chunk["chunk_index"] = i
        chunk["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{doc_id}::{i}"))
    return file_chunks


# --- BGE-M3 SDK ---


def _create_bge_client(bge_url: str):
    """Create BGEM3SyncClient from project SDK."""
    try:
        from telegram_bot.services.bge_m3_client import BGEM3SyncClient

        return BGEM3SyncClient(base_url=bge_url)
    except ImportError:
        return None


def encode_hybrid_sdk(client, texts: list[str]) -> dict[str, list]:
    """Encode via BGEM3SyncClient.encode_hybrid()."""
    result = client.encode_hybrid(texts)
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


# --- Qdrant helpers ---


def preflight_check(client: QdrantClient, collection: str) -> None:
    """Validate collection exists and has required vector configs."""
    if not client.collection_exists(collection):
        print(f"ERROR: Collection '{collection}' does not exist.")
        print("Create it first or check the collection name.")
        sys.exit(1)

    info = client.get_collection(collection)
    vector_names = set()
    if isinstance(info.config.params.vectors, dict):
        vector_names = set(info.config.params.vectors.keys())

    sparse_names = set()
    if info.config.params.sparse_vectors:
        sparse_names = set(info.config.params.sparse_vectors.keys())

    missing = []
    if "dense" not in vector_names:
        missing.append("dense (named vector)")
    if "colbert" not in vector_names:
        missing.append("colbert (named vector)")
    if "bm42" not in sparse_names:
        missing.append("bm42 (sparse vector)")

    if missing:
        print(f"ERROR: Collection '{collection}' missing vectors: {', '.join(missing)}")
        sys.exit(1)


def ensure_payload_indexes(client: QdrantClient, collection: str) -> None:
    """Create keyword payload indexes for filterable fields."""
    for field_name in PAYLOAD_INDEX_FIELDS:
        try:
            client.create_payload_index(
                collection_name=collection,
                field_name=field_name,
                field_schema=PayloadSchemaType.KEYWORD,
                wait=True,
            )
        except Exception as exc:
            print(f"WARNING: payload index ensure failed for {field_name}: {exc}")


def delete_doc_points(client: QdrantClient, collection: str, doc_id: str) -> int:
    """Delete all points for a given doc_id (idempotent re-index)."""
    result = client.delete(
        collection_name=collection,
        points_selector=Filter(
            must=[FieldCondition(key="metadata.doc_id", match=MatchValue(value=doc_id))]
        ),
    )
    return getattr(result, "operation_id", 0)


def _validate_embeddings(chunks: list[dict], embeddings: dict[str, list]) -> None:
    """Fail early on incomplete hybrid embedding payloads."""
    dense = embeddings.get("dense")
    sparse = embeddings.get("sparse")
    colbert = embeddings.get("colbert")

    if dense is None or sparse is None or colbert is None:
        raise ValueError("Embedding count mismatch: dense, sparse, and colbert are required")

    counts = {
        "chunks": len(chunks),
        "dense": len(dense),
        "sparse": len(sparse),
        "colbert": len(colbert),
    }
    expected = counts["chunks"]
    if any(count != expected for name, count in counts.items() if name != "chunks"):
        raise ValueError(
            "Embedding count mismatch: "
            f"chunks={counts['chunks']} dense={counts['dense']} "
            f"sparse={counts['sparse']} colbert={counts['colbert']}"
        )


def upsert_points(
    client: QdrantClient,
    collection: str,
    chunks: list[dict],
    embeddings: dict[str, list],
) -> int:
    """Upload chunks with retry, keeping batch size at 1 for large ColBERT payloads."""
    _validate_embeddings(chunks, embeddings)

    points: list[PointStruct] = []
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
                    "text": chunk["text"],
                    "metadata": {
                        "file_name": chunk["source_file"],
                        "source": chunk["source_file"],
                        "doc_id": chunk["doc_id"],
                        "heading": chunk["heading"],
                        "chunk_id": chunk["chunk_index"],
                    },
                },
            )
        )
    client.upload_points(
        collection_name=collection,
        points=iter(points),
        batch_size=UPLOAD_BATCH_SIZE,
        max_retries=UPLOAD_MAX_RETRIES,
        wait=True,
    )
    return len(points)


# --- Main ---


def main() -> int:
    parser = argparse.ArgumentParser(description="Index local docs via BGE-M3")
    parser.add_argument(
        "--docs-dir",
        default=os.getenv("DOCS_DIR", DEFAULT_DOCS_DIR),
    )
    parser.add_argument("--collection", "-c", default=DEFAULT_COLLECTION)
    parser.add_argument("--bge-url", default=os.getenv("BGE_M3_URL", DEFAULT_BGE_M3_URL))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", DEFAULT_QDRANT_URL))
    parser.add_argument("--batch-size", type=int, default=EMBED_BATCH_SIZE)
    args = parser.parse_args()

    print("=" * 60)
    print("Local Document Indexer (BGE-M3)")
    print("=" * 60)
    print(f"  Docs:       {args.docs_dir}")
    print(f"  Collection: {args.collection}")
    print(f"  BGE-M3:     {args.bge_url}")
    print(f"  Qdrant:     {args.qdrant_url}")
    print()

    # Find .md files
    docs_path = Path(args.docs_dir)
    if not docs_path.exists():
        print(f"Error: directory not found: {args.docs_dir}", file=sys.stderr)
        return 1

    md_files = sorted(docs_path.glob("*.md"))
    if not md_files:
        print(f"Error: no .md files in {args.docs_dir}", file=sys.stderr)
        return 1

    print(f"Found {len(md_files)} .md files")

    ***REMOVED*** preflight
    qdrant = QdrantClient(url=args.qdrant_url, timeout=60)
    preflight_check(qdrant, args.collection)
    ensure_payload_indexes(qdrant, args.collection)
    print("Preflight OK\n")

    # BGE-M3 client
    bge_client = _create_bge_client(args.bge_url)
    use_sdk = bge_client is not None
    if use_sdk:
        print("Using BGEM3SyncClient SDK")
    else:
        print("Using raw HTTP (BGEM3SyncClient not available)")

    # Document-scoped pipeline
    total_points = 0
    try:
        for file_idx, md_file in enumerate(md_files, 1):
            print(f"\n[{file_idx}/{len(md_files)}] {md_file.name}")

            # 1. Chunk
            chunks = load_document_chunks(md_file)
            if not chunks:
                print("  No chunks, skipping")
                continue
            print(f"  {len(chunks)} chunks")

            # 2. Embed
            texts = [c["text"] for c in chunks]
            if use_sdk:
                embeddings = encode_hybrid_sdk(bge_client, texts)
            else:
                embeddings = encode_hybrid_http(texts, args.bge_url, args.batch_size)

            # 3. Delete old points for this doc (idempotent)
            doc_id = md_file.name
            delete_doc_points(qdrant, args.collection, doc_id)

            # 4. Upload new points with retry
            count = upsert_points(qdrant, args.collection, chunks, embeddings)
            total_points += count
            print(f"  Upserted {count} points")
    finally:
        if bge_client is not None:
            bge_client.close()
        qdrant.close()

    print(f"\nDone! Indexed {total_points} points into '{args.collection}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
