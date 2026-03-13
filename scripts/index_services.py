#!/usr/bin/env python3
"""Index services.yaml content into Qdrant for retrieval."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import yaml

from src.ingestion.chunker import Chunk
from src.ingestion.unified.qdrant_writer import QdrantHybridWriter


DEFAULT_SERVICES_PATH = Path("telegram_bot/config/services.yaml")


def load_services(services_path: Path) -> list[tuple[str, dict]]:
    data = yaml.safe_load(services_path.read_text(encoding="utf-8")) or {}
    services = data.get("services", {})
    return [(key, value) for key, value in services.items() if value.get("card_text")]


def build_service_chunks(services_path: Path) -> list[tuple[str, Chunk]]:
    chunks: list[tuple[str, Chunk]] = []
    for index, (service_key, service_data) in enumerate(load_services(services_path)):
        title = str(service_data.get("title", service_key))
        text = str(service_data["card_text"]).strip()
        chunk = Chunk(
            text=f"{title}\n\n{text}",
            chunk_id=index,
            document_name=services_path.name,
            article_number=service_key,
            section=title,
            order=0,
            extra_metadata={"chunk_order": 0, "service_key": service_key},
        )
        chunks.append((service_key, chunk))
    return chunks


def create_writer() -> QdrantHybridWriter:
    return QdrantHybridWriter(
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        qdrant_api_key=os.getenv("QDRANT_API_KEY"),
        voyage_api_key=os.getenv("VOYAGE_API_KEY"),
        bge_m3_url=os.getenv("BGE_M3_URL", "http://localhost:8000"),
        use_local_embeddings=True,
    )


def index_services(
    *,
    writer: QdrantHybridWriter,
    services_path: Path,
    collection_name: str,
) -> int:
    indexed = 0
    source_path = str(services_path)
    for service_key, chunk in build_service_chunks(services_path):
        file_id = f"services.yaml::{service_key}"
        stats = writer.upsert_chunks_sync(
            chunks=[chunk],
            file_id=file_id,
            source_path=source_path,
            file_metadata={
                "file_name": services_path.name,
                "mime_type": "application/yaml",
                "modified_time": str(int(services_path.stat().st_mtime)),
                "content_hash": service_key,
                "service_key": service_key,
                "source": "services.yaml",
            },
            collection_name=collection_name,
        )
        if stats.errors:
            raise RuntimeError("; ".join(stats.errors))
        indexed += stats.points_upserted
    return indexed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--services-path", default=str(DEFAULT_SERVICES_PATH))
    parser.add_argument(
        "--collection",
        default=os.getenv("GDRIVE_COLLECTION_NAME", "gdrive_documents_bge"),
    )
    args = parser.parse_args()

    indexed = index_services(
        writer=create_writer(),
        services_path=Path(args.services_path),
        collection_name=args.collection,
    )
    print(f"Indexed {indexed} services into {args.collection}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
