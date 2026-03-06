#!/usr/bin/env python3
"""Index services.yaml card_text into Qdrant for RAG search.

Usage:
    uv run python scripts/index_services.py

Environment variables:
    QDRANT_URL      Qdrant base URL (default: http://localhost:6333)
    BGE_M3_URL      BGE-M3 API base URL (default: http://localhost:8000)
    COLLECTION      Qdrant collection name (default: gdrive_documents_bge)
"""

from __future__ import annotations

import logging
import os
import uuid

import httpx
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, SparseVector

from telegram_bot.services.content_loader import load_services_config


logger = logging.getLogger(__name__)

COLLECTION = os.getenv("COLLECTION", "gdrive_documents_bge")


def extract_service_documents(config: dict) -> list[dict]:
    """Extract indexable documents from services config.

    Args:
        config: Parsed services.yaml dict.

    Returns:
        List of dicts with keys: point_id, text, metadata, service_key.
        Services without card_text (or with empty card_text) are skipped.
    """
    services = config.get("services", {})
    docs: list[dict] = []
    for key, svc in services.items():
        card_text = svc.get("card_text", "")
        if not card_text:
            continue
        title = svc.get("title", key)
        docs.append(
            {
                "point_id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"services.yaml:{key}")),
                "text": f"{title}\n\n{card_text}",
                "service_key": key,
                "metadata": {
                    "source": "services.yaml",
                    "service_key": key,
                    "title": title,
                },
            }
        )
    return docs


def _embed_texts(texts: list[str], bge_url: str) -> tuple[list[list[float]], list[dict]]:
    """Call BGE-M3 /encode/hybrid and return (dense_vecs, lexical_weights)."""
    resp = httpx.post(
        f"{bge_url}/encode/hybrid",
        json={"texts": texts, "max_length": 512},
        timeout=60.0,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["dense_vecs"], data["lexical_weights"]


def index_services(
    qdrant_url: str = "http://localhost:6333",
    bge_url: str = "http://localhost:8000",
    collection: str = COLLECTION,
) -> None:
    """Load services.yaml, embed card_text, upsert to Qdrant."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    config = load_services_config()
    docs = extract_service_documents(config)

    if not docs:
        logger.info("No service documents found — nothing to index.")
        return

    logger.info("Indexing %d services into '%s'", len(docs), collection)

    texts = [d["text"] for d in docs]
    dense_vecs, lexical_weights = _embed_texts(texts, bge_url)

    points: list[PointStruct] = []
    for doc, dense, sparse in zip(docs, dense_vecs, lexical_weights, strict=True):
        points.append(
            PointStruct(
                id=doc["point_id"],
                vector={
                    "dense": dense,
                    "bm42": SparseVector(
                        indices=sparse["indices"],
                        values=sparse["values"],
                    ),
                },
                payload={
                    "text": doc["text"],
                    **doc["metadata"],
                },
            )
        )

    client = QdrantClient(url=qdrant_url)
    client.upsert(collection_name=collection, points=points)
    logger.info("Done. Upserted %d points.", len(points))


if __name__ == "__main__":
    index_services(
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        bge_url=os.getenv("BGE_M3_URL", "http://localhost:8000"),
        collection=os.getenv("COLLECTION", "gdrive_documents_bge"),
    )
