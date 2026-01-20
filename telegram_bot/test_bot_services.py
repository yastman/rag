#!/usr/bin/env python3
"""Test bot services without Telegram."""

import asyncio

from config import BotConfig
from services import EmbeddingService, FilterExtractor, RetrieverService


async def test_services():
    """Test bot services locally."""
    print("=" * 80)
    print("Testing Telegram Bot Services")
    print("=" * 80)
    print()

    config = BotConfig()

    # 1. Test Filter Extractor
    print("1️⃣  Testing Filter Extractor...")
    extractor = FilterExtractor()

    queries = [
        "покажи квартиры дешевле 100000 евро",
        "3-комнатные в Солнечный берег",
        "студия от 80к до 120к",
    ]

    for query in queries:
        filters = extractor.extract_filters(query)
        print(f"   Query: {query}")
        print(f"   Filters: {filters}")
        print()

    # 2. Test Embedding Service
    print("2️⃣  Testing Embedding Service...")
    embedding_service = EmbeddingService(config.bge_m3_url)

    try:
        query = "покажи дешевые квартиры"
        embedding = await embedding_service.embed_query(query)
        print(f"   Query: {query}")
        print(f"   Embedding dim: {len(embedding)}")
        print(f"   First 5 values: {embedding[:5]}")
        print()
    except Exception as e:
        print(f"   ✗ Error: {e}")
        print()

    # 3. Test Retriever Service
    print("3️⃣  Testing Retriever Service...")
    retriever = RetrieverService(
        url=config.qdrant_url,
        api_key=config.qdrant_api_key,
        collection_name=config.qdrant_collection,
    )

    try:
        # Test with filters
        query = "покажи квартиры дешевле 100000"
        filters = extractor.extract_filters(query)
        embedding = await embedding_service.embed_query(query)

        results = retriever.search(
            query_vector=embedding,
            filters=filters,
            top_k=3,
        )

        print(f"   Query: {query}")
        print(f"   Filters: {filters}")
        print(f"   Results: {len(results)}")
        print()

        for i, result in enumerate(results, 1):
            meta = result["metadata"]
            print(f"   {i}. {meta.get('title', 'N/A')}")
            print(f"      Price: {meta.get('price', 'N/A'):,}€")
            print(f"      Score: {result['score']:.3f}")
            print()

    except Exception as e:
        print(f"   ✗ Error: {e}")
        print()

    # Cleanup
    await embedding_service.close()

    print("=" * 80)
    print("✅ Service tests complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_services())
