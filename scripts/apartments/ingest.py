"""Ingest apartments CSV into Qdrant with BGE-M3 embeddings."""

import csv
import os
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector

from telegram_bot.services.apartment_models import ApartmentRecord
from telegram_bot.services.bge_m3_client import BGEM3SyncClient


COLLECTION = "apartments"
NAMESPACE = uuid.UUID("7ba7b810-9dad-11d1-80b4-00c04fd430c8")
BATCH_SIZE = 32


def generate_point_id(complex_name: str, section: str, apartment_number: str) -> str:
    """Deterministic UUID from complex + section + apartment number."""
    return str(uuid.uuid5(NAMESPACE, f"{complex_name}::{section}::{apartment_number}"))


def ingest(csv_path: str, qdrant_url: str, bge_url: str) -> None:
    client = QdrantClient(url=qdrant_url)
    bge = BGEM3SyncClient(base_url=bge_url)

    # Read CSV
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Loaded {len(rows)} apartments from {csv_path}")

    # Convert to records
    records = [ApartmentRecord.from_raw(row) for row in rows]
    descriptions = [r.to_description() for r in records]

    # Embed in batches
    all_dense, all_sparse, all_colbert = [], [], []
    for i in range(0, len(descriptions), BATCH_SIZE):
        batch = descriptions[i : i + BATCH_SIZE]
        result = bge.encode_hybrid(batch)
        all_dense.extend(result.dense_vecs)
        all_sparse.extend(result.lexical_weights)
        all_colbert.extend(result.colbert_vecs or [])
        print(f"  Embedded {min(i + BATCH_SIZE, len(descriptions))}/{len(descriptions)}")

    # Build points
    points = []
    for rec, dense, sparse, colbert in zip(
        records, all_dense, all_sparse, all_colbert, strict=True
    ):
        point_id = generate_point_id(rec.complex_name, rec.section, rec.apartment_number)
        vector_dict: dict = {
            "dense": dense,
            "bm42": SparseVector(indices=sparse["indices"], values=sparse["values"]),
        }
        if colbert:
            vector_dict["colbert"] = colbert

        points.append(
            PointStruct(
                id=point_id,
                vector=vector_dict,
                payload=rec.to_payload(),
            )
        )

    # Upsert in batches
    for i in range(0, len(points), 100):
        batch = points[i : i + 100]
        client.upsert(collection_name=COLLECTION, points=batch)
        print(f"  Upserted {min(i + 100, len(points))}/{len(points)}")

    print(f"Done. {len(points)} apartments in collection '{COLLECTION}'.")


if __name__ == "__main__":
    ingest(
        csv_path=os.getenv("APARTMENTS_CSV", "data/apartments.csv"),
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        bge_url=os.getenv("BGE_M3_URL", "http://localhost:8000"),
    )
