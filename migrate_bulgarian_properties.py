#!/usr/bin/env python3
"""
Migrate bulgarian_properties collection to n8n-compatible format.

Old format:
{
  "text": "...",
  "record_id": 0,
  "Название": "...",
  "Город": "...",
  ...
}

New format (n8n LangChain compatible):
{
  "page_content": "...",
  "metadata": {
    "record_id": 0,
    "title": "...",
    "city": "...",
    ...
  }
}
"""

import os
import sys
from typing import Any

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams


# Load environment variables
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

# Collection names
SOURCE_COLLECTION = "bulgarian_properties"
TARGET_COLLECTION = "bulgarian_properties_v2"


def migrate_payload(old_payload: dict[str, Any]) -> dict[str, Any]:
    """
    Transform old payload to n8n-compatible format.

    Args:
        old_payload: Old format with Russian field names

    Returns:
        New format with page_content + metadata
    """
    # Extract text content
    page_content = old_payload.get("text", "")

    # Map Russian fields to English metadata
    metadata = {
        "record_id": old_payload.get("record_id"),
        "title": old_payload.get("Название", ""),
        "city": old_payload.get("Город", ""),
        "price_eur": old_payload.get("Цена (€)", ""),
        "rooms": old_payload.get("Комнат", ""),
        "area_m2": old_payload.get("Площадь (м²)", ""),
        "floor": old_payload.get("Этаж", ""),
        "floors_total": old_payload.get("Этажей", ""),
        "distance_to_sea_m": old_payload.get("До моря (м)", ""),
        "fee_eur": old_payload.get("Поддержка (€)", ""),
        "bathrooms": old_payload.get("Санузлов", ""),
        "furnished": old_payload.get("Мебель", ""),
        "all_year": old_payload.get("Круглогодичность", ""),
        "description": old_payload.get("Описание", ""),
        "url": old_payload.get("Ссылка", ""),
    }

    return {"page_content": page_content, "metadata": metadata}


def main():
    """Migrate bulgarian_properties to n8n-compatible format."""
    print("=" * 70)
    print("BULGARIAN PROPERTIES MIGRATION")
    print("=" * 70)
    print(f"Source: {SOURCE_COLLECTION}")
    print(f"Target: {TARGET_COLLECTION}")
    print()

    # Initialize Qdrant client
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    # Check source collection exists
    try:
        source_info = client.get_collection(SOURCE_COLLECTION)
        print(f"✓ Source collection found: {source_info.points_count} points")
    except Exception as e:
        print(f"✗ Error: Source collection not found: {e}")
        sys.exit(1)

    # Create target collection
    print(f"\nCreating target collection: {TARGET_COLLECTION}")
    try:
        # Delete if exists
        try:
            client.delete_collection(TARGET_COLLECTION)
            print(f"  Deleted existing {TARGET_COLLECTION}")
        except Exception:
            pass

        # Create new collection with same vector config
        client.create_collection(
            collection_name=TARGET_COLLECTION,
            vectors_config=VectorParams(
                size=1024,  # Same as source (BGE-M3)
                distance=Distance.COSINE,
            ),
        )
        print(f"✓ Created collection: {TARGET_COLLECTION}")
    except Exception as e:
        print(f"✗ Error creating collection: {e}")
        sys.exit(1)

    # Migrate points
    print(f"\nMigrating points from {SOURCE_COLLECTION}...")

    batch_size = 100
    offset = None
    total_migrated = 0

    while True:
        # Scroll through source collection
        result = client.scroll(
            collection_name=SOURCE_COLLECTION,
            limit=batch_size,
            offset=offset,
            with_payload=True,
            with_vectors=True,
        )

        points = result[0]
        offset = result[1]

        if not points:
            break

        # Transform points
        new_points = []
        for point in points:
            old_payload = point.payload
            new_payload = migrate_payload(old_payload)

            new_point = PointStruct(
                id=point.id,  # Keep same UUID
                vector=point.vector,  # Keep same vector
                payload=new_payload,
            )
            new_points.append(new_point)

        # Upsert to target collection
        client.upsert(collection_name=TARGET_COLLECTION, points=new_points)

        total_migrated += len(new_points)
        print(f"  Migrated {total_migrated} points...")

        if offset is None:
            break

    print(f"\n✓ Migration complete: {total_migrated} points migrated")

    # Verify migration
    print("\nVerifying migration...")
    target_info = client.get_collection(TARGET_COLLECTION)
    print(f"  Target collection: {target_info.points_count} points")

    if target_info.points_count == source_info.points_count:
        print("✓ Point counts match!")
    else:
        print("⚠ Warning: Point counts don't match!")

    # Show sample from target collection
    print(f"\nSample from {TARGET_COLLECTION}:")
    sample = client.scroll(
        collection_name=TARGET_COLLECTION,
        limit=1,
        with_payload=True,
        with_vectors=False,
    )[0]

    if sample:
        point = sample[0]
        print(f"  ID: {point.id}")
        print(f"  page_content: {point.payload.get('page_content', '')[:100]}...")
        print(f"  metadata keys: {list(point.payload.get('metadata', {}).keys())}")

    print("\n" + "=" * 70)
    print("MIGRATION COMPLETE")
    print("=" * 70)
    print("\nNext steps:")
    print("1. In n8n, update Qdrant Vector Store node:")
    print(f"   - Collection Name: {TARGET_COLLECTION}")
    print("2. Test with AI Agent")
    print()


if __name__ == "__main__":
    main()
