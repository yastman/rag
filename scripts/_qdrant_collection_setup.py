"""Shared Qdrant client and payload-index setup primitives."""

import os
from collections.abc import Iterable

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import PayloadSchemaType


PayloadIndexFields = Iterable[tuple[PayloadSchemaType, Iterable[str]]]
GDRIVE_PAYLOAD_INDEX_FIELDS = (
    (
        PayloadSchemaType.KEYWORD,
        (
            "file_id",
            "metadata.file_id",
            "metadata.doc_id",
            "metadata.source",
            "metadata.file_name",
            "metadata.mime_type",
            "metadata.topic",
            "metadata.doc_type",
        ),
    ),
    (PayloadSchemaType.INTEGER, ("metadata.order", "metadata.chunk_id")),
)

APARTMENT_PAYLOAD_INDEX_FIELDS = (
    (
        PayloadSchemaType.KEYWORD,
        (
            "complex_name",
            "city",
            "section",
            "apartment_number",
            "view_primary",
            "view_tags",
        ),
    ),
    (PayloadSchemaType.INTEGER, ("rooms", "floor")),
    (PayloadSchemaType.FLOAT, ("price_eur", "area_m2")),
    (PayloadSchemaType.BOOL, ("is_furnished", "is_promotion")),
)

PAYLOAD_INDEX_FIELDS_BY_COLLECTION = {
    "gdrive_documents_bge": GDRIVE_PAYLOAD_INDEX_FIELDS,
    "apartments": APARTMENT_PAYLOAD_INDEX_FIELDS,
}


def payload_index_types(field_map: PayloadIndexFields) -> dict[str, str]:
    """Flatten a payload-index map into Qdrant's expected field types."""
    return {
        field_name: field_schema.value
        for field_schema, fields in field_map
        for field_name in fields
    }


def get_qdrant_client(*, timeout: int = 60, announce: bool = True) -> QdrantClient:
    """Create a Qdrant client from environment variables."""
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY")
    if announce:
        print(f"Connecting to Qdrant at {url}...")
    return QdrantClient(url=url, api_key=api_key, timeout=timeout)


def collection_exists(client: QdrantClient, collection_name: str) -> bool:
    """Check whether a collection exists."""
    try:
        client.get_collection(collection_name)
        return True
    except (UnexpectedResponse, Exception):
        return False


def delete_collection(client: QdrantClient, collection_name: str) -> None:
    """Delete a collection when it exists."""
    if collection_exists(client, collection_name):
        print(f"Deleting existing collection: {collection_name}")
        client.delete_collection(collection_name)
        print(f"  Deleted: {collection_name}")


def create_payload_indexes(
    client: QdrantClient, collection_name: str, field_map: PayloadIndexFields
) -> None:
    """Create every payload index, reporting all failures to the caller."""
    print("Creating payload indexes...")
    failures: list[str] = []
    for field_schema, fields in field_map:
        for field_name in fields:
            try:
                client.create_payload_index(
                    collection_name=collection_name,
                    field_name=field_name,
                    field_schema=field_schema,
                )
                print(f"  Created {field_schema.value} index: {field_name}")
            except Exception as error:
                failures.append(f"{field_name}: {error}")
    if failures:
        raise RuntimeError("could not create payload indexes: " + "; ".join(failures))
