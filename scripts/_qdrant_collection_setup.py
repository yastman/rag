"""Shared Qdrant client and payload-index setup primitives.

The payload-index field maps below are lifted from the canonical contracts in
``src.runtime.qdrant.contracts`` (#3333) — setup, readiness, bootstrap, and
the index audit all consume the same definitions.
"""

import os
from collections.abc import Iterable

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import PayloadSchemaType

from src.runtime.qdrant.contracts import (
    APARTMENTS_PAYLOAD_INDEXES,
    KNOWLEDGE_PAYLOAD_INDEXES,
)


PayloadIndexFields = Iterable[tuple[PayloadSchemaType, Iterable[str]]]


def _to_field_map(
    index_map: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[tuple[PayloadSchemaType, tuple[str, ...]], ...]:
    """Lift a canonical ``(schema_type, fields)`` map into SDK schema types."""
    return tuple(
        (PayloadSchemaType(schema_type), tuple(fields)) for schema_type, fields in index_map
    )


GDRIVE_PAYLOAD_INDEX_FIELDS = _to_field_map(KNOWLEDGE_PAYLOAD_INDEXES)

APARTMENT_PAYLOAD_INDEX_FIELDS = _to_field_map(APARTMENTS_PAYLOAD_INDEXES)

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
