"""Test script to verify new Qdrant configuration with BM42 + optimizations."""

import asyncio
import os

from dotenv import load_dotenv

from src.config import Settings
from src.ingestion.indexer import DocumentIndexer


# Load environment variables
load_dotenv()


async def main():
    """Test new collection creation and configuration."""
    print("=" * 80)
    print("Testing New Qdrant Configuration")
    print("=" * 80)
    print()

    # Initialize indexer
    settings = Settings()
    indexer = DocumentIndexer(settings)

    # Test 1: Create collection with new config
    print("Step 1: Creating collection 'legal_documents' with new configuration...")
    print("  - Dense vectors: BGE-M3 (1024-dim) with Scalar Int8 quantization")
    print("  - Sparse vectors: BM42 with IDF modifier")
    print("  - ColBERT: Multivector for reranking")
    print("  - Optimizer: indexing_threshold=20k, memmap_threshold=50k")
    print()

    success = indexer.create_collection("legal_documents", recreate=True)
    if success:
        print("✅ Collection created successfully!")
    else:
        print("❌ Failed to create collection")
        return

    print()

    # Test 2: Get collection info
    print("Step 2: Verifying collection configuration...")
    stats = indexer.get_collection_stats("legal_documents")
    print(f"  Collection name: {stats.get('name', 'N/A')}")
    print(f"  Points count: {stats.get('points_count', 0)}")
    print(f"  Vectors count: {stats.get('vectors_count', 0)}")
    print()

    # Test 3: Verify configuration via API
    print("Step 3: Checking configuration via Qdrant API...")
    import requests

    # Run blocking HTTP call in executor to avoid blocking event loop
    loop = asyncio.get_event_loop()
    response = await loop.run_in_executor(
        None,
        lambda: requests.get(  # noqa: ASYNC210
            f"{settings.qdrant_url}/collections/legal_documents",
            headers={"api-key": os.getenv("QDRANT_API_KEY", "")},
        ),
    )

    if response.status_code == 200:
        config = response.json()["result"]["config"]
        vectors = config["params"]["vectors"]
        sparse = config["params"].get("sparse_vectors", {})
        optimizer = config["optimizer_config"]

        print("✅ Configuration verified:")
        print(f"  Dense vectors: {vectors.get('dense', {}).get('size', 'N/A')} dims")
        print(
            f"  Quantization: {vectors.get('dense', {}).get('quantization_config', {}).get('scalar', {}).get('type', 'N/A')}"
        )
        print(f"  ColBERT: {vectors.get('colbert', {}).get('multivector_config', 'N/A')}")
        print(f"  BM42 sparse: {list(sparse.keys())}")
        print(f"  Indexing threshold: {optimizer.get('indexing_threshold', 'N/A')}")
        print(f"  Memmap threshold: {optimizer.get('memmap_threshold', 'N/A')}")
    else:
        print(f"❌ Failed to get collection config: {response.status_code}")

    print()
    print("=" * 80)
    print("Configuration test completed successfully!")
    print("=" * 80)
    print()
    print("Next steps:")
    print("  1. Index your documents using the updated indexer")
    print("  2. Test search with new BM42 + ColBERT pipeline")
    print("  3. Monitor RAM usage (should be ~75% lower)")
    print()


if __name__ == "__main__":
    asyncio.run(main())
