#!/usr/bin/env python3
"""
Create Payload Indexes for Qdrant Collections

Qdrant 2025 Best Practice: Create payload indexes for fields used in filtering.
Payload indexes provide 10-100x speedup for filtering operations.

Index Types:
- INTEGER: For numeric fields (article_number, chapter_number, etc.)
- KEYWORD: For exact string matching (tags, categories)

Based on: https://qdrant.tech/documentation/concepts/indexing/
"""

import sys

import requests


# Import configuration
sys.path.append("/srv/contextual_rag")
from config import COLLECTION_BASELINE, COLLECTION_CONTEXTUAL_KG, QDRANT_API_KEY, QDRANT_URL


def create_payload_index(
    collection_name: str, field_name: str, field_type: str = "integer"
) -> dict:
    """
    Create a payload index for a specific field in a Qdrant collection.

    Args:
        collection_name: Name of the Qdrant collection
        field_name: Name of the payload field to index
        field_type: Type of index ("integer", "keyword", "text", "bool", "geo", "datetime")

    Returns:
        Response JSON from Qdrant API
    """
    url = f"{QDRANT_URL}/collections/{collection_name}/index"
    headers = {"api-key": QDRANT_API_KEY}

    payload = {"field_name": field_name, "field_schema": field_type}

    print(f"Creating {field_type.upper()} index for '{field_name}' in '{collection_name}'...")

    try:
        response = requests.put(url, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        print("✓ Index created successfully")
        return response.json()
    except requests.exceptions.HTTPError as e:
        if "already exists" in str(e).lower() or response.status_code == 409:
            print("⚠️  Index already exists (skipping)")
            return {"status": "already_exists"}
        print(f"✗ Error: {e}")
        print(f"  Response: {response.text}")
        raise


def create_all_indexes(collection_name: str):
    """
    Create all recommended payload indexes for a collection.

    Indexes created:
    - article_number (INTEGER): For filtering by article
    - chapter_number (INTEGER): For filtering by chapter
    - section_number (INTEGER): For filtering by section
    - book_number (INTEGER): For filtering by book
    """
    print("=" * 80)
    print(f"Creating Payload Indexes for Collection: {collection_name}")
    print("=" * 80)
    print()

    # Define fields to index
    index_fields = [
        ("article_number", "integer"),
        ("chapter_number", "integer"),
        ("section_number", "integer"),
        ("book_number", "integer"),
    ]

    # Create each index
    for field_name, field_type in index_fields:
        try:
            create_payload_index(collection_name, field_name, field_type)
        except Exception as e:
            print(f"⚠️  Warning: Failed to create index for {field_name}: {e}")
        print()

    print("=" * 80)
    print("✅ Payload Index Creation Complete")
    print("=" * 80)
    print()


def list_collection_indexes(collection_name: str) -> dict:
    """
    List all existing indexes for a collection.

    Args:
        collection_name: Name of the Qdrant collection

    Returns:
        Collection info including indexes
    """
    url = f"{QDRANT_URL}/collections/{collection_name}"
    headers = {"api-key": QDRANT_API_KEY}

    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()

    return response.json()


def verify_indexes(collection_name: str):
    """
    Verify that all indexes were created successfully.

    Args:
        collection_name: Name of the Qdrant collection
    """
    print("=" * 80)
    print(f"Verifying Indexes for Collection: {collection_name}")
    print("=" * 80)
    print()

    try:
        collection_info = list_collection_indexes(collection_name)
        payload_schema = collection_info.get("result", {}).get("payload_schema", {})

        if not payload_schema:
            print("⚠️  No payload indexes found")
            return

        print("Existing Payload Indexes:")
        for field_name, field_info in payload_schema.items():
            field_type = field_info.get("data_type", "unknown")
            print(f"  ✓ {field_name}: {field_type}")

        print()
    except Exception as e:
        print(f"✗ Error verifying indexes: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create payload indexes for Qdrant collections")
    parser.add_argument(
        "--collection",
        type=str,
        help=f"Collection name (default: both '{COLLECTION_BASELINE}' and '{COLLECTION_CONTEXTUAL_KG}')",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing indexes, don't create new ones",
    )

    args = parser.parse_args()

    # Determine which collections to process
    if args.collection:
        collections = [args.collection]
    else:
        collections = [COLLECTION_BASELINE, COLLECTION_CONTEXTUAL_KG]

    # Process each collection
    for collection in collections:
        if args.verify_only:
            verify_indexes(collection)
        else:
            create_all_indexes(collection)
            verify_indexes(collection)

    print()
    print("=" * 80)
    print("🎯 Next Steps:")
    print("=" * 80)
    print("1. Run evaluation A/B test to measure impact:")
    print("   cd /srv/app/evaluation")
    print("   python run_ab_test.py")
    print()
    print("2. Check index usage in Qdrant queries with 'filter' parameter")
    print("3. Expected improvement: 10-100x faster filtering on indexed fields")
    print("=" * 80)
