#!/usr/bin/env python3
"""Setup Qdrant payload indexes for fast filtering."""

import sys
from pathlib import Path


# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from qdrant_client import QdrantClient, models

from telegram_bot.config import BotConfig


def setup_indexes():
    """Create payload indexes for apartment metadata fields."""
    config = BotConfig()

    # Initialize Qdrant client
    if config.qdrant_api_key:
        client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key)
    else:
        client = QdrantClient(url=config.qdrant_url)

    collection_name = config.qdrant_collection

    print(f"Setting up payload indexes for collection: {collection_name}")
    print("=" * 80)

    # Define indexes to create
    indexes = [
        {
            "field_name": "metadata.source_type",
            "field_schema": models.PayloadSchemaType.KEYWORD,
            "description": "Source type (csv_row, docx_chunk)",
        },
        {
            "field_name": "metadata.jurisdiction",
            "field_schema": models.PayloadSchemaType.KEYWORD,
            "description": "Jurisdiction code (bg, ua, eu)",
        },
        {
            "field_name": "metadata.audience",
            "field_schema": models.PayloadSchemaType.KEYWORD,
            "description": "Target audience (client, internal)",
        },
        {
            "field_name": "metadata.language",
            "field_schema": models.PayloadSchemaType.KEYWORD,
            "description": "Document language",
        },
        {
            "field_name": "metadata.city",
            "field_schema": models.PayloadSchemaType.KEYWORD,
            "description": "City name (Солнечный берег, Несебр)",
        },
        {
            "field_name": "metadata.price",
            "field_schema": models.PayloadSchemaType.INTEGER,
            "description": "Price in euros",
        },
        {
            "field_name": "metadata.rooms",
            "field_schema": models.PayloadSchemaType.INTEGER,
            "description": "Number of rooms",
        },
        {
            "field_name": "metadata.area",
            "field_schema": models.PayloadSchemaType.FLOAT,
            "description": "Area in square meters",
        },
        {
            "field_name": "metadata.floor",
            "field_schema": models.PayloadSchemaType.INTEGER,
            "description": "Floor number",
        },
        {
            "field_name": "metadata.distance_to_sea",
            "field_schema": models.PayloadSchemaType.INTEGER,
            "description": "Distance to sea in meters",
        },
        {
            "field_name": "metadata.maintenance",
            "field_schema": models.PayloadSchemaType.FLOAT,
            "description": "Maintenance cost in euros",
        },
        {
            "field_name": "metadata.bathrooms",
            "field_schema": models.PayloadSchemaType.INTEGER,
            "description": "Number of bathrooms",
        },
        {
            "field_name": "metadata.furniture",
            "field_schema": models.PayloadSchemaType.KEYWORD,
            "description": "Furniture availability (Есть)",
        },
        {
            "field_name": "metadata.year_round",
            "field_schema": models.PayloadSchemaType.KEYWORD,
            "description": "Year-round availability (Да)",
        },
    ]

    # Create each index
    success_count = 0
    for idx in indexes:
        field_name = idx["field_name"]
        field_schema = idx["field_schema"]
        description = idx["description"]

        try:
            print(f"\n📍 Creating index: {field_name}")
            print(f"   Type: {field_schema}")
            print(f"   Description: {description}")

            client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_schema,
            )

            print("   ✅ Success!")
            success_count += 1

        except Exception as e:
            error_msg = str(e)
            if "already exists" in error_msg.lower():
                print("   ℹ️  Index already exists, skipping")
                success_count += 1
            else:
                print(f"   ❌ Error: {e}")

    print("\n" + "=" * 80)
    print(f"✅ Created {success_count}/{len(indexes)} indexes successfully!")
    print("\nIndexes enable fast filtering on:")
    print("  • City (keyword match)")
    print("  • Jurisdiction, audience, language (keyword match)")
    print("  • Price, rooms, area (range filters)")
    print("  • Distance to sea (range filter)")
    print("  • Maintenance cost (range filter)")
    print("  • Bathrooms (exact match)")
    print("  • Furniture, year-round (keyword match)")
    print("\nYour RAG bot will now filter only CSV rows (real apartments)!")


if __name__ == "__main__":
    setup_indexes()
