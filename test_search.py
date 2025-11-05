#!/usr/bin/env python3
"""Test search with BGE-M3 embeddings (dense + sparse + colbert)."""

import asyncio

from src.config import Settings
from src.ingestion.indexer import DocumentIndexer


async def main():
    """Test hybrid search with BGE-M3."""
    print("=" * 80)
    print("Testing Hybrid Search with BGE-M3")
    print("=" * 80)
    print()

    # Initialize
    settings = Settings()
    indexer = DocumentIndexer(settings)

    # Test query
    query = "What is the main topic of this document?"
    print(f"Query: {query}")
    print()

    # Generate query embeddings using BGE-M3
    print("Step 1: Generating query embeddings...")
    embeddings = await indexer._embed_texts([query])
    query_emb = embeddings[0]

    print(f"  ✓ Dense: {len(query_emb['dense_vecs'])} dims")
    print(f"  ✓ Sparse: {len(query_emb['lexical_weights'])} indices")
    print(f"  ✓ ColBERT: {query_emb['colbert_vecs'].shape}")
    print()

    # Prepare sparse vector
    sparse_indices = list(query_emb["lexical_weights"].keys())
    sparse_values = list(query_emb["lexical_weights"].values())

    # Import required types
    from qdrant_client.models import SparseVector

    # Test 1: Dense vector search
    print("Step 2: Testing dense vector search...")
    dense_results = indexer.client.query_points(
        collection_name="legal_documents",
        query=query_emb["dense_vecs"].tolist(),
        using="dense",
        limit=3,
        with_payload=True,
    )
    print(f"  ✓ Found {len(dense_results.points)} results")
    if dense_results.points:
        print(f"  Top score: {dense_results.points[0].score:.4f}")
        print(f"  Text preview: {dense_results.points[0].payload['page_content'][:100]}...")
    print()

    # Test 2: Sparse vector search (BM42)
    print("Step 3: Testing sparse vector search (BM42)...")
    sparse_results = indexer.client.query_points(
        collection_name="legal_documents",
        query=SparseVector(indices=sparse_indices, values=sparse_values),
        using="bm42",
        limit=3,
        with_payload=True,
    )
    print(f"  ✓ Found {len(sparse_results.points)} results")
    if sparse_results.points:
        print(f"  Top score: {sparse_results.points[0].score:.4f}")
    print()

    # Test 3: ColBERT multivector search
    print("Step 4: Testing ColBERT multivector search...")
    colbert_results = indexer.client.query_points(
        collection_name="legal_documents",
        query=query_emb["colbert_vecs"].tolist(),
        using="colbert",
        limit=3,
        with_payload=True,
    )
    print(f"  ✓ Found {len(colbert_results.points)} results")
    if colbert_results.points:
        print(f"  Top score: {colbert_results.points[0].score:.4f}")
    print()

    # Test 4: Hybrid search with RRF
    print("Step 5: Testing hybrid search (RRF fusion)...")
    from qdrant_client.models import FusionQuery, Prefetch

    hybrid_results = indexer.client.query_points(
        collection_name="legal_documents",
        prefetch=[
            # Dense vector search
            Prefetch(
                query=query_emb["dense_vecs"].tolist(),
                using="dense",
                limit=10,
            ),
            # Sparse vector search
            Prefetch(
                query=SparseVector(indices=sparse_indices, values=sparse_values),
                using="bm42",
                limit=10,
            ),
        ],
        query=FusionQuery(fusion="rrf"),  # Reciprocal Rank Fusion
        limit=3,
        with_payload=True,
    )
    print(f"  ✓ Found {len(hybrid_results.points)} results")
    if hybrid_results.points:
        print(f"  Top score: {hybrid_results.points[0].score:.4f}")
        print(f"  Text: {hybrid_results.points[0].payload['page_content'][:150]}...")
    print()

    print("=" * 80)
    print("✅ All search tests passed!")
    print("=" * 80)
    print()
    print("Summary:")
    print("  ✓ Dense vector search: Working")
    print("  ✓ Sparse (BM42) search: Working")
    print("  ✓ ColBERT multivector: Working")
    print("  ✓ Hybrid RRF fusion: Working")
    print()


if __name__ == "__main__":
    asyncio.run(main())
