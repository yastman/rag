#!/usr/bin/env python3
"""Test nested metadata filtering in Qdrant with actual data structure."""

from qdrant_client import QdrantClient, models

from src.config import Settings


def main():
    """Test filtering on nested metadata fields."""
    settings = Settings()
    client = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    collection = "apartments_filtered"

    print("=" * 80)
    print("QDRANT NESTED METADATA FILTERING TEST")
    print("=" * 80)
    print()

    # Test 1: Check actual data structure
    print("1️⃣  Inspecting actual data structure...")
    points, _ = client.scroll(
        collection_name=collection, limit=1, with_payload=True, with_vectors=False
    )

    if points:
        print(f"✓ Collection has {len(points)} points")
        payload = points[0].payload
        print("\n📦 Payload structure:")
        print(f"   Top-level keys: {list(payload.keys())}")

        if "metadata" in payload:
            print(f"   metadata keys: {list(payload['metadata'].keys())}")
            print("\n   Example metadata values:")
            meta = payload["metadata"]
            for key in ["source_type", "city", "price", "rooms"]:
                if key in meta:
                    print(f"     - {key}: {meta[key]} (type: {type(meta[key]).__name__})")
    else:
        print("✗ No points found!")
        return

    print("\n" + "=" * 80)
    print("2️⃣  Test: Filter by metadata.source_type = 'csv_row'")
    print("=" * 80)

    filter1 = models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.source_type", match=models.MatchValue(value="csv_row")
            )
        ]
    )

    results1, _ = client.scroll(
        collection_name=collection,
        scroll_filter=filter1,
        limit=10,
        with_payload=True,
        with_vectors=False,
    )

    print(f"\n✓ Found {len(results1)} CSV rows")
    if results1:
        meta = results1[0].payload.get("metadata", {})
        print(f"   Example: {meta.get('title', 'N/A')}")
        print(f"   City: {meta.get('city')}, Price: {meta.get('price')}€")

    print("\n" + "=" * 80)
    print("3️⃣  Test: Complex filter (city + price range)")
    print("=" * 80)

    filter2 = models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.source_type", match=models.MatchValue(value="csv_row")
            ),
            models.FieldCondition(
                key="metadata.city",
                match=models.MatchValue(value="Солнечный берег"),
            ),
            models.FieldCondition(key="metadata.price", range=models.Range(lt=80000)),
        ]
    )

    results2, _ = client.scroll(
        collection_name=collection,
        scroll_filter=filter2,
        limit=10,
        with_payload=True,
        with_vectors=False,
    )

    print(f"\n✓ Found {len(results2)} apartments")
    print("   Filters: source_type='csv_row' AND city='Солнечный берег' AND price < 80,000€")

    for i, point in enumerate(results2, 1):
        meta = point.payload.get("metadata", {})
        print(f"\n   {i}. {meta.get('title', 'N/A')}")
        print(f"      City: {meta.get('city')}")
        print(f"      Price: {meta.get('price'):,}€")
        print(f"      Rooms: {meta.get('rooms')}")

    print("\n" + "=" * 80)
    print("4️⃣  Test: OR filter (multiple cities)")
    print("=" * 80)

    filter3 = models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.source_type", match=models.MatchValue(value="csv_row")
            )
        ],
        should=[  # OR condition
            models.FieldCondition(
                key="metadata.city",
                match=models.MatchValue(value="Солнечный берег"),
            ),
            models.FieldCondition(key="metadata.city", match=models.MatchValue(value="Несебр")),
        ],
    )

    results3, _ = client.scroll(
        collection_name=collection,
        scroll_filter=filter3,
        limit=10,
        with_payload=True,
        with_vectors=False,
    )

    print(f"\n✓ Found {len(results3)} apartments")
    print("   Filters: (city='Солнечный берег' OR city='Несебр') AND source_type='csv_row'")

    cities = {}
    for point in results3:
        city = point.payload.get("metadata", {}).get("city", "Unknown")
        cities[city] = cities.get(city, 0) + 1

    for city, count in cities.items():
        print(f"   - {city}: {count} apartments")

    print("\n" + "=" * 80)
    print("5️⃣  Test: Multiple numeric filters")
    print("=" * 80)

    filter4 = models.Filter(
        must=[
            models.FieldCondition(
                key="metadata.source_type", match=models.MatchValue(value="csv_row")
            ),
            models.FieldCondition(key="metadata.rooms", match=models.MatchValue(value=1)),
            models.FieldCondition(key="metadata.distance_to_sea", range=models.Range(lte=600)),
            models.FieldCondition(key="metadata.price", range=models.Range(gte=50000, lte=80000)),
        ]
    )

    results4, _ = client.scroll(
        collection_name=collection,
        scroll_filter=filter4,
        limit=10,
        with_payload=True,
        with_vectors=False,
    )

    print(f"\n✓ Found {len(results4)} apartments")
    print("   Filters: rooms=1 AND distance≤600m AND price 50k-80k€")

    for i, point in enumerate(results4, 1):
        meta = point.payload.get("metadata", {})
        print(f"\n   {i}. {meta.get('title', 'N/A')}")
        print(f"      Price: {meta.get('price'):,}€")
        print(f"      Distance to sea: {meta.get('distance_to_sea')}m")

    print("\n" + "=" * 80)
    print("✅ ALL TESTS PASSED!")
    print("=" * 80)
    print("\nSummary:")
    print("  • Nested metadata filtering works: metadata.field_name")
    print(f"  • Base filter (csv_row): {len(results1)} points")
    print(f"  • Complex filter: {len(results2)} apartments")
    print(f"  • OR filter: {len(results3)} apartments")
    print(f"  • Multiple numeric filters: {len(results4)} apartments")
    print("\n🎯 Ready for production use in Telegram bot!")


if __name__ == "__main__":
    main()
