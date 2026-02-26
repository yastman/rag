"""Create apartments Qdrant collection with vectors and payload indexes."""

from qdrant_client import QdrantClient, models
from qdrant_client.models import (
    BinaryQuantization,
    BinaryQuantizationConfig,
    Distance,
    HnswConfigDiff,
    Modifier,
    MultiVectorComparator,
    MultiVectorConfig,
    SparseVectorParams,
    VectorParams,
)


COLLECTION_NAME = "apartments"
DENSE_DIM = 1024


def create_apartments_collection(client: QdrantClient) -> None:
    """Create collection mirroring gdrive_documents_bge vector schema."""
    if client.collection_exists(COLLECTION_NAME):
        print(f"Collection '{COLLECTION_NAME}' already exists, skipping creation")
        return

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": VectorParams(
                size=DENSE_DIM,
                distance=Distance.COSINE,
                hnsw_config=HnswConfigDiff(m=16, ef_construct=200, on_disk=False),
                quantization_config=BinaryQuantization(
                    binary=BinaryQuantizationConfig(always_ram=True)
                ),
                on_disk=True,
            ),
            "colbert": VectorParams(
                size=DENSE_DIM,
                distance=Distance.COSINE,
                multivector_config=MultiVectorConfig(comparator=MultiVectorComparator.MAX_SIM),
                hnsw_config=HnswConfigDiff(m=0),
                on_disk=True,
            ),
        },
        sparse_vectors_config={
            "bm42": SparseVectorParams(modifier=Modifier.IDF),
        },
    )
    print(f"Created collection: {COLLECTION_NAME}")


def create_payload_indexes(client: QdrantClient) -> None:
    """Create indexes for apartment payload fields (top-level, no metadata. prefix)."""
    indexes = {
        # Keyword (facets + exact match)
        "complex_name": "keyword",
        "city": "keyword",
        "section": "keyword",
        "apartment_number": "keyword",
        "view_primary": "keyword",
        "view_tags": "keyword",
        # Integer (lookup + range)
        "rooms": models.PayloadSchemaType.INTEGER,
        "floor": models.PayloadSchemaType.INTEGER,
        # Float (range + order_by)
        "price_eur": models.PayloadSchemaType.FLOAT,
        "area_m2": models.PayloadSchemaType.FLOAT,
        # Bool
        "is_furnished": "bool",
        "is_promotion": models.PayloadSchemaType.BOOL,
    }

    for field_name, schema in indexes.items():
        try:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=schema,
            )
            print(f"  Index: {field_name} ({schema})")
        except Exception as e:
            print(f"  Warning: {field_name}: {e}")


if __name__ == "__main__":
    import os

    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    client = QdrantClient(url=url)
    create_apartments_collection(client)
    create_payload_indexes(client)
    print("Done.")
