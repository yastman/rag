#!/usr/bin/env python3
"""Index test properties into Qdrant for E2E testing."""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)


# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram_bot.services import VoyageService


load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
COLLECTION_NAME = "contextual_bulgaria_test"


async def main():
    """Index test properties."""
    # Load properties
    data_path = Path("data/test_properties.json")
    if not data_path.exists():
        print("Error: data/test_properties.json not found.")
        print("Run: python scripts/generate_test_properties.py")
        sys.exit(1)

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    properties = data["properties"]
    print(f"Loaded {len(properties)} properties")

    # Initialize Voyage for embeddings
    voyage = VoyageService(
        api_key=VOYAGE_API_KEY,
        model_docs="voyage-4-large",
    )

    # Generate embeddings for descriptions
    descriptions = [p["description"] for p in properties]
    print("Generating embeddings...")
    embeddings = await voyage.embed_documents(descriptions)
    print(f"Generated {len(embeddings)} embeddings (dim={len(embeddings[0])})")

    # Initialize Qdrant
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)

    # Recreate collection
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in collections:
        client.delete_collection(COLLECTION_NAME)
        print(f"Deleted existing collection: {COLLECTION_NAME}")

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={"dense": VectorParams(size=len(embeddings[0]), distance=Distance.COSINE)},
    )
    print(f"Created collection: {COLLECTION_NAME}")

    # Index points
    points = []
    for i, (prop, embedding) in enumerate(zip(properties, embeddings, strict=True)):
        point = PointStruct(
            id=i,
            vector={"dense": embedding},
            payload={
                "page_content": prop["description"],
                "text": prop["description"],
                "metadata": {
                    "id": prop["id"],
                    "title": prop["title"],
                    "city": prop["city"],
                    "district": prop["district"],
                    "rooms": prop["rooms"],
                    "price": prop["price"],
                    "area": prop["area"],
                    "floor": prop["floor"],
                    "total_floors": prop["total_floors"],
                    "distance_to_sea": prop["distance_to_sea"],
                    "year_built": prop["year_built"],
                    "features": prop["features"],
                },
            },
        )
        points.append(point)

    # Batch upsert
    batch_size = 50
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch)
        print(f"Indexed {min(i + batch_size, len(points))}/{len(points)}")

    # Verify
    info = client.get_collection(COLLECTION_NAME)
    print(f"\nCollection '{COLLECTION_NAME}': {info.points_count} points indexed")

    # Test search
    test_query = "студия в Солнечный берег до 50000"
    test_embedding = await voyage.embed_query(test_query)
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=("dense", test_embedding),
        limit=3,
    )
    print(f"\nTest search for '{test_query}':")
    for r in results:
        meta = r.payload.get("metadata", {})
        print(f"  - {meta.get('title')}: {meta.get('price'):,} EUR (score: {r.score:.3f})")


if __name__ == "__main__":
    asyncio.run(main())
