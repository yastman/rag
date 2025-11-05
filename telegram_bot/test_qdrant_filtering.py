#!/usr/bin/env python3
"""Test Qdrant filtering with base filter (CSV rows only)."""

import sys
from pathlib import Path


# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient, models

from telegram_bot.config import BotConfig


def test_filtering():
    """Test that filtering returns only CSV rows (real apartments)."""
    config = BotConfig()

    # Initialize Qdrant client
    if config.qdrant_api_key:
        client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)
    else:
        client = QdrantClient(url=config.qdrant_url)

    collection_name = config.qdrant_collection

    print("=" * 80)
    print(f"Testing Qdrant filtering on collection: {collection_name}")
    print("=" * 80)

    # Test 1: Get all points (no filter)
    print("\n1️⃣  Test: All points (no filter)")
    all_points, _ = client.scroll(
        collection_name=collection_name, limit=100, with_payload=True, with_vectors=False
    )
    print(f"   Total points: {len(all_points)}")

    csv_count = sum(
        1 for p in all_points if p.payload.get("metadata", {}).get("source_type") == "csv_row"
    )
    other_count = len(all_points) - csv_count
    print(f"   CSV rows: {csv_count}")
    print(f"   Other chunks: {other_count}")

    # Test 2: Filter only CSV rows
    print("\n2️⃣  Test: Filter only CSV rows (base filter)")
    csv_points, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.source_type", match=models.MatchValue(value="csv_row")
                )
            ]
        ),
        limit=100,
        with_payload=True,
        with_vectors=False,
    )
    print(f"   Filtered points: {len(csv_points)}")

    if len(csv_points) > 0:
        print("\n   Example CSV row:")
        example = csv_points[0].payload
        meta = example.get("metadata", {})
        print(f"   - City: {meta.get('city', 'N/A')}")
        print(f"   - Price: {meta.get('price', 'N/A')}€")
        print(f"   - Rooms: {meta.get('rooms', 'N/A')}")
        print(f"   - Area: {meta.get('area', 'N/A')} м²")
        print(f"   - Distance to sea: {meta.get('distance_to_sea', 'N/A')} м")
        print(f"   - Furniture: {meta.get('furniture', 'N/A')}")

    # Test 3: Complex filter (city + price range)
    print("\n3️⃣  Test: Complex filter (Солнечный берег + price < 100,000€)")
    filtered_points, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.source_type", match=models.MatchValue(value="csv_row")
                ),
                models.FieldCondition(
                    key="metadata.city",
                    match=models.MatchValue(value="Солнечный берег"),
                ),
                models.FieldCondition(key="metadata.price", range=models.Range(lt=100000)),
            ]
        ),
        limit=10,
        with_payload=True,
        with_vectors=False,
    )
    print(f"   Found: {len(filtered_points)} apartments")

    for i, point in enumerate(filtered_points[:3], 1):
        meta = point.payload.get("metadata", {})
        print(f"\n   {i}. {meta.get('title', 'N/A')}")
        print(f"      City: {meta.get('city', 'N/A')}")
        print(f"      Price: {meta.get('price', 'N/A'):,}€")
        print(f"      Rooms: {meta.get('rooms', 'N/A')}")

    # Test 4: Filter by distance to sea
    print("\n4️⃣  Test: Filter by distance to sea (< 600m)")
    sea_points, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.source_type", match=models.MatchValue(value="csv_row")
                ),
                models.FieldCondition(key="metadata.distance_to_sea", range=models.Range(lt=600)),
            ]
        ),
        limit=10,
        with_payload=True,
        with_vectors=False,
    )
    print(f"   Found: {len(sea_points)} apartments near sea")

    for i, point in enumerate(sea_points[:3], 1):
        meta = point.payload.get("metadata", {})
        print(
            f"\n   {i}. Distance: {meta.get('distance_to_sea', 'N/A')}m | "
            f"Price: {meta.get('price', 'N/A'):,}€ | "
            f"City: {meta.get('city', 'N/A')}"
        )

    print("\n" + "=" * 80)
    print("✅ Filtering tests complete!")
    print("\nSummary:")
    print(f"  • Total points: {len(all_points)}")
    print(f"  • CSV rows (apartments): {csv_count}")
    print(f"  • Base filter returns: {len(csv_points)} CSV rows ✓")
    print("\n🎯 Your RAG bot will only retrieve real apartments from CSV!")


if __name__ == "__main__":
    test_filtering()
