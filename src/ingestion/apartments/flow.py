"""Flow primitives for apartments ingestion.

Formats hybrid text and builds Qdrant-ready point payloads.
Used by incremental runner / future CocoIndex wiring.
"""

from __future__ import annotations

import uuid

from telegram_bot.services.apartment_models import ApartmentRecord


COLLECTION = "apartments"
NAMESPACE = uuid.UUID("7ba7b810-9dad-11d1-80b4-00c04fd430c8")


def generate_point_id(complex_name: str, section: str, apartment_number: str) -> str:
    """Deterministic UUID5 from complex + section + apartment number."""
    return str(uuid.uuid5(NAMESPACE, f"{complex_name}::{section}::{apartment_number}"))


def format_apartment_text(record: ApartmentRecord) -> str:
    """Hybrid text serialization for BGE-M3: structured prefix + NL description.

    Structured prefix helps sparse/lexical retrieval (exact match on numbers).
    NL body helps dense/semantic retrieval (conceptual queries like "уютная у моря").
    """
    # Structured prefix for sparse retrieval
    price_k = int(record.price_eur / 1000)
    prefix = f"[{record.rooms}BR|{record.area_m2}m2|{price_k}kEUR]"

    # NL body (Russian) for dense retrieval — reuses existing to_description()
    body = record.to_description()

    # Promotion marker
    promo = " Акция!" if record.is_promotion else ""

    return f"{prefix} {body}{promo}"


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
        point_id = generate_point_id(rec.complex_name, rec.section, rec.apartment_number)
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
