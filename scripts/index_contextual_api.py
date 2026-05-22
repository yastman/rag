#!/usr/bin/env python3
"""
Index contextual JSON files using BGE-M3 API (fast, no local model loading).

Uses the BGE-M3 API service on port 8000 instead of loading model locally.
Much faster startup - model is already loaded in Docker container.

Usage:
    python scripts/index_contextual_api.py docs/processed/ --collection contextual_bulgaria
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    HnswConfigDiff,
    Modifier,
    MultiVectorComparator,
    MultiVectorConfig,
    PointStruct,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)


# Configuration
QDRANT_URL = "http://localhost:6333"
BGE_M3_URL = "http://localhost:8000"
BATCH_SIZE = 8  # Texts per API call


async def get_embeddings(texts: list[str]) -> list[dict]:
    """Get embeddings from BGE-M3 API."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{BGE_M3_URL}/encode/hybrid",
            json={"texts": texts},
        )
        response.raise_for_status()
        return response.json()


def create_collection(client: QdrantClient, collection_name: str, recreate: bool = False):
    """Create Qdrant collection with optimized BGE-M3 vectors.

    Optimization: ColBERT uses hnsw_config.m=0 (no HNSW index) because:
    - ColBERT is used for reranking, not first-stage retrieval
    - Brute-force MaxSim on 50 candidates is fast enough
    - Saves RAM and speeds up upsert operations
    """
    if recreate and client.collection_exists(collection_name):
        client.delete_collection(collection_name)
        print(f"  Deleted existing collection: {collection_name}")

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "dense": VectorParams(
                    size=1024,
                    distance=Distance.COSINE,
                    # Dense uses HNSW for fast first-stage retrieval
                ),
                "colbert": VectorParams(
                    size=1024,
                    distance=Distance.COSINE,
                    multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                    # OPTIMIZATION: Disable HNSW for ColBERT (reranker only)
                    hnsw_config=HnswConfigDiff(m=0),
                ),
            },
            sparse_vectors_config={
                "bm42": SparseVectorParams(modifier=Modifier.IDF),
            },
        )
        print(f"  Created collection: {collection_name} (ColBERT m=0 optimized)")
    else:
        print(f"  Using existing collection: {collection_name}")


async def index_file(client: QdrantClient, json_path: Path, collection_name: str) -> dict:
    """Index a single JSON file."""
    print(f"\n  Processing: {json_path.name}")

    # Load JSON
    with open(json_path, encoding="utf-8") as f:
        doc = json.load(f)

    chunks = doc["chunks"]
    print(f"    {len(chunks)} chunks")

    # Process chunks one at a time (ColBERT vectors are huge)
    indexed = 0
    for _i, chunk in enumerate(chunks):
        text = chunk["text_for_embedding"]

        # Get embedding for single chunk
        emb_response = await get_embeddings([text])

        dense_vec = emb_response["dense_vecs"][0]
        lexical = emb_response["lexical_weights"][0]
        colbert_vec = emb_response["colbert_vecs"][0]

        point = PointStruct(
            id=hash(f"{doc['source']}_{chunk['chunk_id']}") % (2**63),
            vector={
                "dense": dense_vec,
                "colbert": colbert_vec,
                "bm42": SparseVector(indices=lexical["indices"], values=lexical["values"]),
            },
            payload={
                "page_content": chunk["text"],
                "text_for_embedding": chunk["text_for_embedding"],
                "metadata": {
                    "source": doc["source"],
                    "chunk_id": chunk["chunk_id"],
                    "topic": chunk["topic"],
                    "keywords": chunk["keywords"],
                    "context": chunk["context"],
                    "source_type": "vtt_contextual",
                },
            },
        )
        client.upsert(collection_name=collection_name, points=[point])
        indexed += 1

    print(f"    Indexed {indexed} points")
    return {"file": json_path.name, "chunks": len(chunks)}


async def main(args):
    print("\n" + "=" * 60)
    print("Contextual Retrieval Indexer (API Mode)")
    print("=" * 60)

    # Check API
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{BGE_M3_URL}/health")
        if resp.json().get("status") != "ok":
            print("ERROR: BGE-M3 API not ready")
            return 1
    print(f"\n  BGE-M3 API: {BGE_M3_URL} ✓")

    # Connect to Qdrant
    qdrant = QdrantClient(url=QDRANT_URL)
    print(f"  Qdrant: {QDRANT_URL} ✓")

    # Create collection
    collection_name = args.collection
    print(f"\n  Collection: {collection_name}")
    create_collection(qdrant, collection_name, recreate=args.recreate)

    # Find JSON files
    input_path = Path(args.input)
    json_files = [input_path] if input_path.is_file() else sorted(input_path.glob("*.json"))

    print(f"\n  Found {len(json_files)} JSON files")

    # Index each file
    results = []
    total_chunks = 0
    for json_path in json_files:
        try:
            result = await index_file(qdrant, json_path, collection_name)
            results.append(result)
            total_chunks += result["chunks"]
        except Exception as e:
            print(f"    ERROR: {e}")
            results.append({"file": json_path.name, "error": str(e)})

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"  Files processed: {len(results)}")
    print(f"  Total chunks: {total_chunks}")

    # Collection stats
    info = qdrant.get_collection(collection_name)
    print(f"  Points in collection: {info.points_count}")

    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index contextual JSON using BGE-M3 API")
    parser.add_argument("input", help="JSON file or directory")
    parser.add_argument("--collection", "-c", default="contextual_bulgaria", help="Collection name")
    parser.add_argument("--recreate", action="store_true", help="Recreate collection")

    args = parser.parse_args()
    sys.exit(asyncio.run(main(args)))
