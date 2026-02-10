#!/usr/bin/env python3
"""
Check if collections have sparse vectors and try to add them if possible.
"""

import sys

import requests


sys.path.append("/srv/contextual_rag")
from config import QDRANT_API_KEY, QDRANT_URL


headers = {"api-key": QDRANT_API_KEY}


def get_collection_info(collection_name: str):
    """Get collection configuration."""
    response = requests.get(
        f"{QDRANT_URL}/collections/{collection_name}",
        headers=headers,
    )
    if response.status_code == 200:
        return response.json()["result"]
    print(f"❌ Error getting collection info: {response.text}")
    return None


def try_update_collection_with_sparse(collection_name: str):
    """Try to add sparse vectors to existing collection (will likely fail)."""
    update_payload = {"sparse_vectors": {"sparse": {"modifier": "idf"}}}

    response = requests.patch(
        f"{QDRANT_URL}/collections/{collection_name}",
        json=update_payload,
        headers=headers,
    )

    print(f"\n📝 Attempt to add sparse vectors to '{collection_name}':")
    print(f"   Status code: {response.status_code}")

    if response.status_code == 200:
        print("   ✅ SUCCESS: Sparse vectors added!")
        return True
    print(f"   ❌ FAILED: {response.text}")
    return False


def main():
    print("=" * 80)
    print("SPARSE VECTORS CHECK")
    print("=" * 80)

    # Check one test collection
    collection_name = "uk_civil_code_v2"

    print(f"\n🔍 Checking collection: {collection_name}")
    info = get_collection_info(collection_name)

    if info:
        # Check current configuration
        config = info["config"]["params"]

        print("\n📊 Current configuration:")
        print(f"   Named vectors: {list(config['vectors'].keys())}")

        if "sparse_vectors" in config:
            print(f"   ✅ Sparse vectors: {list(config['sparse_vectors'].keys())}")
        else:
            print("   ❌ Sparse vectors: MISSING")

            # Try to add sparse vectors (expected to fail)
            try_update_collection_with_sparse(collection_name)

    print("\n" + "=" * 80)
    print("CONCLUSION:")
    print("=" * 80)

    print("""
According to Qdrant documentation, sparse_vectors_config can ONLY be set
during collection creation (CreateCollection API).

The UpdateCollection API does NOT support adding sparse vectors to existing
collections.

SOLUTION: We need to:
1. Recreate all collections using create_collection_enhanced.py
2. Re-ingest all documents with sparse vectors enabled
""")


if __name__ == "__main__":
    main()
