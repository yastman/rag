#!/usr/bin/env python3
"""Test Qdrant filtering with structured metadata."""

import asyncio

from qdrant_client import QdrantClient, models

from src.config import Settings


async def main():
    settings = Settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )

    collection = "apartments_filtered"

    print("=" * 80)
    print(f"Testing filtering on collection: {collection}")
    print("=" * 80)
    print()

    # 1. Check that structured metadata exists
    print("1️⃣  Checking structured metadata...")
    points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.source_type", match=models.MatchValue(value="csv_row")
                )
            ]
        ),
        limit=1,
        with_payload=True,
        with_vectors=False,
    )

    if points:
        print(f"   ✓ Found {len(points)} CSV rows")
        print(f"   Metadata keys: {list(points[0].payload['metadata'].keys())}")
        print()
        print("   Example metadata:")
        meta = points[0].payload["metadata"]
        for key in ["title", "city", "price", "rooms", "area", "furnished"]:
            if key in meta:
                print(f"     {key}: {meta[key]} (type: {type(meta[key]).__name__})")
    else:
        print("   ✗ No CSV rows found!")
        return

    print()
    print("=" * 80)
    print("2️⃣  Test query: Квартиры дешевле 100 000 евро")
    print("=" * 80)

    # Filter: price < 100000 AND source_type = csv_row
    filtered_points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.source_type", match=models.MatchValue(value="csv_row")
                ),
                models.FieldCondition(key="metadata.price", range=models.Range(lt=100000)),
            ]
        ),
        limit=10,
        with_payload=True,
        with_vectors=False,
    )

    print(f"\nFound {len(filtered_points)} apartments < 100 000€:")
    print("-" * 80)
    for point in filtered_points:
        meta = point.payload["metadata"]
        print(f"\n📍 {meta.get('title', 'N/A')}")
        print(f"   Цена: {meta.get('price', 'N/A'):,}€")
        print(f"   Город: {meta.get('city', 'N/A')}")
        print(f"   Комнат: {meta.get('rooms', 'N/A')}")
        print(f"   Площадь: {meta.get('area', 'N/A')} м²")

    print()
    print("=" * 80)
    print("3️⃣  Test query: 3-комнатные квартиры в Солнечный берег")
    print("=" * 80)

    filtered_points, _ = client.scroll(
        collection_name=collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="metadata.source_type", match=models.MatchValue(value="csv_row")
                ),
                models.FieldCondition(key="metadata.rooms", match=models.MatchValue(value=3)),
                models.FieldCondition(
                    key="metadata.city", match=models.MatchValue(value="Солнечный берег")
                ),
            ]
        ),
        limit=10,
        with_payload=True,
        with_vectors=False,
    )

    print(f"\nFound {len(filtered_points)} apartments:")
    print("-" * 80)
    for point in filtered_points:
        meta = point.payload["metadata"]
        print(f"\n📍 {meta.get('title', 'N/A')}")
        print(f"   Цена: {meta.get('price', 'N/A'):,}€")
        print(f"   Комнат: {meta.get('rooms', 'N/A')}")
        print(f"   Площадь: {meta.get('area', 'N/A')} м²")
        print(f"   До моря: {meta.get('distance_to_sea', 'N/A')} м")

    print()
    print("=" * 80)
    print("✅ Filtering test complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
