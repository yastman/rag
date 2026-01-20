#!/usr/bin/env python3
"""Verify chunks in Qdrant collection."""

import asyncio

from qdrant_client import QdrantClient

from src.config import Settings


async def main():
    settings = Settings()
    client = QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key,
    )

    collection = "bulgarian_properties_v3"

    # Get collection info
    print(f"Collection: {collection}")
    print("=" * 80)

    info = client.get_collection(collection)
    print(f"Points count: {info.points_count}")
    print(f"Vectors config: {info.config.params.vectors}")
    print()

    # Scroll through all points
    points, _next_offset = client.scroll(
        collection_name=collection,
        limit=100,
        with_payload=True,
        with_vectors=False,
    )

    print(f"Retrieved {len(points)} points:")
    print("=" * 80)

    # Group by document
    by_doc = {}
    for point in points:
        doc_name = point.payload.get("metadata", {}).get("document_name", "unknown")
        if doc_name not in by_doc:
            by_doc[doc_name] = []
        by_doc[doc_name].append(point)

    # Show stats per document
    for doc_name, doc_points in sorted(by_doc.items()):
        print(f"\n📄 {doc_name}")
        print(f"   Chunks: {len(doc_points)}")

        # Show chunk sizes
        chunk_sizes = [len(p.payload.get("page_content", "")) for p in doc_points]
        avg_size = sum(chunk_sizes) / len(chunk_sizes) if chunk_sizes else 0
        print(f"   Avg chunk size: {avg_size:.0f} chars")
        print(f"   Min/Max: {min(chunk_sizes)}/{max(chunk_sizes)} chars")

        # Show first chunk sample
        if doc_points:
            first_content = doc_points[0].payload.get("page_content", "")
            preview = first_content[:150].replace("\n", " ")
            print(f"   First chunk: {preview}...")

    print("\n" + "=" * 80)
    print("✅ Verification complete")


if __name__ == "__main__":
    asyncio.run(main())
