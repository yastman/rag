#!/usr/bin/env python3
"""
Extract ground truth dataset from Qdrant collection.
Creates a mapping: article_number -> [chunk_ids]
"""

import json
import os
from collections import defaultdict

from qdrant_client import QdrantClient

from src.config import Settings


# Load Qdrant config without failing module import in test environments.
try:
    _settings = Settings()
    QDRANT_URL = _settings.qdrant_url
    QDRANT_API_KEY = _settings.qdrant_api_key or ""
except ValueError:
    QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")


def _qdrant_url() -> str:
    """Return Qdrant base URL from resolved settings/environment."""
    return QDRANT_URL or "http://localhost:6333"


def _qdrant_api_key() -> str:
    """Return Qdrant API key from resolved settings/environment."""
    return QDRANT_API_KEY or ""


def _make_client() -> QdrantClient:
    """Create a QdrantClient from resolved settings/environment."""
    url = _qdrant_url()
    api_key = _qdrant_api_key()
    if api_key:
        return QdrantClient(url=url, api_key=api_key)
    return QdrantClient(url=url)


def extract_articles(collection_name: str) -> dict[str, list[str]]:
    """
    Extract all articles and their chunk IDs from Qdrant collection.

    Returns:
        Dict mapping article_number to list of chunk IDs
    """
    print(f"Extracting articles from collection: {collection_name}")

    client = _make_client()

    # Get all points from collection with scroll API
    offset = None
    articles = defaultdict(list)
    total_points = 0

    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            offset=offset,
            limit=100,
            with_payload=["article_number", "chunk_id", "text"],
            with_vectors=False,
        )

        if not points:
            break

        # Process points
        for point in points:
            payload = point.payload or {}
            article = payload.get("article_number")
            if article:
                chunk_id = payload.get("chunk_id", point.id)
                text_preview = payload.get("text", "")[:100]

                articles[str(article)].append(
                    {"chunk_id": chunk_id, "point_id": point.id, "text_preview": text_preview}
                )
                total_points += 1

        # Check if there are more points
        offset = next_offset
        if offset is None:
            break

        print(f"  Processed {total_points} points...", end="\r")

    print(f"\nExtracted {len(articles)} articles from {total_points} chunks")

    return dict(articles)  # type: ignore[arg-type]


def print_statistics(articles: dict[str, list[str]]):
    """Print statistics about the extracted articles."""
    print("\nDataset Statistics:")
    print(f"  Total articles: {len(articles)}")
    print(f"  Total chunks: {sum(len(chunks) for chunks in articles.values())}")

    # Article distribution
    chunks_per_article = [len(chunks) for chunks in articles.values()]
    print("  Chunks per article:")
    print(f"    Min: {min(chunks_per_article)}")
    print(f"    Max: {max(chunks_per_article)}")
    print(f"    Avg: {sum(chunks_per_article) / len(chunks_per_article):.1f}")

    # Sample articles
    print("\nSample articles:")
    for article_num in sorted(articles.keys(), key=lambda x: int(x))[:5]:
        print(f"    Article {article_num}: {len(articles[article_num])} chunks")


def main():
    """Main entry point."""
    collection_name = "ukraine_criminal_code_zai_full"

    # Extract articles
    articles = extract_articles(collection_name)

    # Print statistics
    print_statistics(articles)

    # Save to file
    output_file = "/home/admin/contextual_rag/evaluation/data/ground_truth_articles.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\nSaved to: {output_file}")

    # Create simplified mapping (article -> first chunk only) for quick tests
    simple_mapping = {article: chunks[0]["point_id"] for article, chunks in articles.items()}
    simple_output = "/home/admin/contextual_rag/evaluation/data/article_to_chunk_mapping.json"
    with open(simple_output, "w", encoding="utf-8") as f:
        json.dump(simple_mapping, f, ensure_ascii=False, indent=2)

    print(f"Simplified mapping saved to: {simple_output}")
    print("\nGround truth extraction completed!")


if __name__ == "__main__":
    main()
