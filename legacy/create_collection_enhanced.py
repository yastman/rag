#!/usr/bin/env python3
"""
Create Enhanced Qdrant Collection with Contextual + KG Schema
"""

import requests

from config import (
    COLBERT_VECTOR_SIZE,
    DEFAULT_COLLECTION,
    DENSE_VECTOR_SIZE,
    QDRANT_API_KEY,
    QDRANT_URL,
)


def create_enhanced_collection(collection_name: str | None = None):
    """Create Qdrant collection with enhanced schema for contextual retrieval + KG."""

    # Use default collection if not specified
    if collection_name is None:
        collection_name = DEFAULT_COLLECTION

    # Collection configuration with quantization
    config = {
        "vectors": {
            "dense": {
                "size": DENSE_VECTOR_SIZE,
                "distance": "Cosine",
                "on_disk": True,
                "hnsw_config": {"m": 16, "ef_construct": 200},
                "quantization_config": {
                    "scalar": {"type": "int8", "quantile": 0.99, "always_ram": True}
                },
            },
            "colbert": {
                "size": COLBERT_VECTOR_SIZE,
                "distance": "Cosine",
                "multivector_config": {"comparator": "max_sim"},
                # Disable HNSW for multivector (Qdrant 2025 best practice)
                # ColBERT used only for reranking, not as first-stage search
                "hnsw_config": {
                    "m": 0  # Disables HNSW graph, saves memory & indexing time
                },
            },
        },
        "sparse_vectors": {"sparse": {"modifier": "idf"}},
    }

    # Delete if exists
    try:
        requests.delete(
            f"{QDRANT_URL}/collections/{collection_name}",
            headers={"api-key": QDRANT_API_KEY},
            timeout=10,
        )
        print(f"✓ Deleted existing collection: {collection_name}")
    except Exception:
        pass  # Collection doesn't exist, that's fine

    # Create collection
    response = requests.put(
        f"{QDRANT_URL}/collections/{collection_name}",
        json=config,
        headers={"api-key": QDRANT_API_KEY},
        timeout=30,
    )

    response.raise_for_status()
    print(f"✅ Created collection: {collection_name}")
    print(f"   - Dense vectors: {DENSE_VECTOR_SIZE}D (INT8 quantized)")
    print(f"   - ColBERT multivectors: {COLBERT_VECTOR_SIZE}D")
    print("   - Sparse vectors: BM25 (IDF modifier)")
    print("   - Payload schema: contextual + KG metadata")

    return response.json()


if __name__ == "__main__":
    print("=" * 80)
    print("CREATING ENHANCED QDRANT COLLECTION")
    print("=" * 80)
    create_enhanced_collection()
    print("=" * 80)
    print("✅ Collection ready for contextual ingestion!")
