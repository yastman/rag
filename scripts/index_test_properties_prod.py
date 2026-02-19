#!/usr/bin/env python3
"""Safely add test properties to production Qdrant collection.

This script UPSERTS (adds/updates) test properties without deleting existing data.
Uses ID range 900000-900999 to avoid conflicts with existing points.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct


# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from telegram_bot.services import VoyageService


load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
COLLECTION_NAME = "gdrive_documents_bge"  # Production collection!
ID_OFFSET = 900000  # Start IDs from 900000 to avoid conflicts


async def main():
    """Add test properties to production collection."""
    # Load properties
    data_path = Path("data/test_properties.json")
    if not data_path.exists():
        print("Error: data/test_properties.json not found.")
        print("Run: python scripts/generate_test_properties.py")
        sys.exit(1)

    with open(data_path) as f:
        data = json.load(f)

    properties = data["properties"]
    print(f"Loaded {len(properties)} properties")
    print(f"Target collection: {COLLECTION_NAME} (PRODUCTION)")
    print(f"ID range: {ID_OFFSET} - {ID_OFFSET + len(properties) - 1}")
    print()

    # Initialize Voyage for embeddings
    voyage = VoyageService(api_key=VOYAGE_API_KEY)

    # Generate embeddings
    print("Generating embeddings...")
    texts = [p["description"] for p in properties]
    embeddings = await voyage.embed_documents(texts)
    print(f"Generated {len(embeddings)} embeddings (dim={len(embeddings[0])})")

    # Connect to Qdrant
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY or None)

    # Check collection exists
    collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in collections:
        print(f"Error: Collection '{COLLECTION_NAME}' not found!")
        print(f"Available: {collections}")
        sys.exit(1)

    # Get current collection info
    info = client.get_collection(COLLECTION_NAME)
    print(f"Collection '{COLLECTION_NAME}': {info.points_count} existing points")

    # Prepare points with offset IDs
    points = []
    for i, (prop, emb) in enumerate(zip(properties, embeddings, strict=True)):
        point_id = ID_OFFSET + i
        points.append(
            PointStruct(
                id=point_id,
                vector={"dense": emb},
                payload={
                    "text": prop["description"],
                    "title": prop["title"],
                    "city": prop["city"],
                    "price": prop["price"],
                    "rooms": prop["rooms"],
                    "area": prop["area"],
                    "distance_to_sea": prop["distance_to_sea"],
                    "district": prop.get("district", ""),
                    "features": prop.get("features", []),
                    "is_test_data": True,  # Mark as test data for easy cleanup
                },
            )
        )

    # Upsert in batches
    batch_size = 50
    for i in range(0, len(points), batch_size):
        batch = points[i : i + batch_size]
        client.upsert(collection_name=COLLECTION_NAME, points=batch, wait=True)
        print(f"Upserted {min(i + batch_size, len(points))}/{len(points)}")

    # Verify
    info = client.get_collection(COLLECTION_NAME)
    print()
    print(f"Collection '{COLLECTION_NAME}': {info.points_count} total points")

    # Test search
    test_query = "студия в Солнечный берег до 50000"
    query_emb = await voyage.embed_query(test_query)
    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=("dense", query_emb),
        limit=3,
        query_filter={"must": [{"key": "is_test_data", "match": {"value": True}}]},
    )

    print(f"\nTest search for '{test_query}' (test data only):")
    for r in results:
        print(
            f"  - {r.payload.get('title', 'N/A')}: {r.payload.get('price', 'N/A')} EUR (score: {r.score:.3f})"
        )


if __name__ == "__main__":
    asyncio.run(main())
