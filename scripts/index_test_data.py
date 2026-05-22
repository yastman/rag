#!/usr/bin/env python3
"""Index test data from JSON into Qdrant."""

import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
BGE_M3_URL = os.getenv("BGE_M3_URL", "http://localhost:8000")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "test_documents")


async def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Get dense embeddings from BGE-M3 service."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(f"{BGE_M3_URL}/encode/dense", json={"texts": texts})
        response.raise_for_status()
        return response.json()["dense_vecs"]


def create_collection(client: QdrantClient, collection_name: str, vector_size: int = 1024):
    """Create or recreate Qdrant collection."""
    # Delete if exists
    collections = [c.name for c in client.get_collections().collections]
    if collection_name in collections:
        client.delete_collection(collection_name)
        print(f"Deleted existing collection: {collection_name}")

    # Create new with named vector "dense" (required by RetrieverService)
    client.create_collection(
        collection_name=collection_name,
        vectors_config={"dense": VectorParams(size=vector_size, distance=Distance.COSINE)},
    )
    print(f"Created collection: {collection_name} (with named vector 'dense')")


async def index_documents(json_path: str):
    """Index documents from JSON file."""
    # Load data
    with open(json_path) as f:
        data = json.load(f)

    documents = data["documents"]
    print(f"Loaded {len(documents)} documents from {json_path}")

    # Get embeddings
    texts = [doc["content"] for doc in documents]
    print("Getting embeddings...")
    embeddings = await get_embeddings(texts)
    print(f"Got {len(embeddings)} embeddings")

    # Create collection
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)
    create_collection(client, COLLECTION_NAME)

    # Index points with named vector and RetrieverService-compatible payload
    points = [
        PointStruct(
            id=i,
            vector={"dense": embeddings[i]},
            payload={
                "page_content": doc["content"],  # RetrieverService expects this key
                "metadata": {
                    "id": doc["id"],
                    "title": doc["title"],
                    **doc.get("metadata", {}),
                },
            },
        )
        for i, doc in enumerate(documents)
    ]

    client.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Indexed {len(points)} documents into {COLLECTION_NAME}")

    # Verify
    info = client.get_collection(COLLECTION_NAME)
    print(f"Collection info: {info.points_count} points")


if __name__ == "__main__":
    json_path = sys.argv[1] if len(sys.argv) > 1 else "data/test/sample_articles.json"
    asyncio.run(index_documents(json_path))
