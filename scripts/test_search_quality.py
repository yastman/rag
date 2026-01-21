#!/usr/bin/env python3
"""Test search quality after m=0 optimization."""

import asyncio

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import Prefetch, SparseVector


QDRANT_URL = "http://localhost:6333"
BGE_M3_URL = "http://localhost:8000"
COLLECTION = "contextual_bulgaria"

TEST_QUERIES = [
    ("Как открыть фирму в Болгарии?", "Зачем открывать фирму"),
    ("Налог НДС ДДС при сдаче через Букинг", "Налоговая ловушка"),
    ("ВНЖ для фрилансеров Digital Nomad", "Digital Nomad"),
    ("Такса поддержки что это", "поддержки"),
    ("Сколько стоит открыть фирму в Болгарии", "300 евро"),
]


async def get_embeddings(text: str) -> dict:
    """Get embeddings from BGE-M3 API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(f"{BGE_M3_URL}/encode/hybrid", json={"texts": [text]})
        return resp.json()


async def test_search():
    """Run test queries and verify results."""
    client = QdrantClient(url=QDRANT_URL)

    print("=" * 60)
    print("Search Quality Test (m=0 optimization)")
    print("=" * 60)

    passed = 0
    failed = 0

    for query, expected_in_result in TEST_QUERIES:
        emb = await get_embeddings(query)

        # Hybrid search with ColBERT reranking
        results = client.query_points(
            collection_name=COLLECTION,
            prefetch=[
                Prefetch(query=emb["dense_vecs"][0], using="dense", limit=20),
                Prefetch(
                    query=SparseVector(
                        indices=emb["lexical_weights"][0]["indices"],
                        values=emb["lexical_weights"][0]["values"],
                    ),
                    using="bm42",
                    limit=20,
                ),
            ],
            query=emb["colbert_vecs"][0],
            using="colbert",
            limit=3,
        )

        top_result = results.points[0] if results.points else None

        if top_result:
            topic = top_result.payload.get("metadata", {}).get("topic", "")
            text = top_result.payload.get("page_content", "")
            score = top_result.score

            found = (
                expected_in_result.lower() in topic.lower()
                or expected_in_result.lower() in text.lower()
            )
            status = "PASS" if found else "CHECK"

            if found:
                passed += 1
            else:
                failed += 1

            print(f"\nQ: {query}")
            print(f"   -> Topic: {topic}")
            print(f"   -> Score: {score:.2f}")
            print(f"   -> {status}")
        else:
            failed += 1
            print(f"\nQ: {query}")
            print("   -> NO RESULTS")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} need review")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    success = asyncio.run(test_search())
    exit(0 if success else 1)
