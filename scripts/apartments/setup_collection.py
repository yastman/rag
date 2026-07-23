"""Create apartments Qdrant collection with vectors and payload indexes."""

import argparse
import sys

from qdrant_client import QdrantClient
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

from scripts._qdrant_collection_setup import (
    APARTMENT_PAYLOAD_INDEX_FIELDS,
    get_qdrant_client,
)
from scripts._qdrant_collection_setup import (
    create_payload_indexes as create_collection_payload_indexes,
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
    """Create indexes for the apartment payload contract."""
    create_collection_payload_indexes(client, COLLECTION_NAME, APARTMENT_PAYLOAD_INDEX_FIELDS)


def main(argv: list[str] | None = None) -> int:
    """Create the apartments collection and its payload indexes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)

    client = get_qdrant_client()
    create_apartments_collection(client)
    create_payload_indexes(client)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
