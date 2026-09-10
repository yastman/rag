"""Flow primitives for apartments ingestion.

Formats hybrid text and builds Qdrant-ready point payloads.
Used by incremental runner.

Point identity comes from the canonical authority
``src.runtime.qdrant.contracts.apartment_point_id`` (#3333) so ingestion,
readiness, and the shipped demo catalog address identical points.
"""

from __future__ import annotations

from src.models.apartment import ApartmentRecord
from src.runtime.qdrant.contracts import APARTMENTS_COLLECTION, apartment_point_id


COLLECTION = APARTMENTS_COLLECTION


def format_apartment_text(record: ApartmentRecord) -> str:
    """Hybrid text serialization for BGE-M3: structured prefix + NL description.

    Delegates to ApartmentRecord.to_hybrid_description() — single source of truth.
    """
    return record.to_hybrid_description()


def build_ingestion_batch(
    records: list[ApartmentRecord],
    dense_vecs: list[list[float]],
    sparse_weights: list[dict],
    colbert_vecs: list[list[list[float]]],
) -> list[dict]:
    """Build Qdrant point dicts from records and their embeddings.

    Returns list of dicts with keys: id, vector, payload.
    """
    from qdrant_client.models import SparseVector

    points = []
    for rec, dense, sparse, colbert in zip(
        records, dense_vecs, sparse_weights, colbert_vecs, strict=True
    ):
        point_id = apartment_point_id(rec.complex_name, rec.section, rec.apartment_number)
        vector_dict: dict = {
            "dense": dense,
            "bm42": SparseVector(indices=sparse["indices"], values=sparse["values"]),
        }
        if colbert:
            vector_dict["colbert"] = colbert

        payload = rec.to_payload()
        payload["description_hybrid"] = format_apartment_text(rec)

        points.append({"id": point_id, "vector": vector_dict, "payload": payload})

    return points
