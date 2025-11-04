"""
CSV to Qdrant Indexer using Docling.

This script processes CSV files through Docling, chunks the data,
generates embeddings using BGE-M3, and indexes to Qdrant.

Usage:
    python src/ingestion/csv_to_qdrant.py --input demo_BG.csv --collection bulgarian_properties

Features:
- Docling CSV parsing
- Smart text generation from structured data
- BGE-M3 embeddings (1024-dim)
- Qdrant indexing with metadata
- Progress tracking
"""

import asyncio
import csv
import os
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from sentence_transformers import SentenceTransformer


@dataclass
class CSVRecord:
    """Single CSV record with metadata."""

    data: dict[str, Any]
    text: str
    record_id: int


class CSVToQdrantIndexer:
    """
    Process CSV files and index to Qdrant.

    Pipeline:
    1. Read CSV file
    2. Convert each row to text representation
    3. Generate embeddings with BGE-M3
    4. Index to Qdrant with full metadata
    """

    def __init__(
        self,
        qdrant_url: str = "http://localhost:6333",
        qdrant_api_key: Optional[str] = None,
    ):
        """Initialize indexer with Qdrant connection."""
        # Load environment variables
        load_dotenv()

        self.qdrant_url = qdrant_url
        self.qdrant_api_key = qdrant_api_key or os.getenv("QDRANT_API_KEY")

        # Initialize clients
        self.client = QdrantClient(url=self.qdrant_url, api_key=self.qdrant_api_key)
        self.embedding_model = SentenceTransformer("BAAI/bge-m3")

        print("✓ Initialized CSV to Qdrant Indexer")
        print(f"  - Qdrant URL: {self.qdrant_url}")
        print("  - Embedding model: BAAI/bge-m3 (1024-dim)")

    def read_csv(self, file_path: Path) -> list[CSVRecord]:
        """
        Read CSV file and convert to records.

        Args:
            file_path: Path to CSV file

        Returns:
            List of CSV records with text representation
        """
        records = []

        with open(file_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for idx, row in enumerate(reader):
                # Convert row to natural language text
                text = self._row_to_text(row)

                record = CSVRecord(data=row, text=text, record_id=idx)
                records.append(record)

        print(f"✓ Read {len(records)} records from {file_path}")
        return records

    def _row_to_text(self, row: dict[str, Any]) -> str:
        """
        Convert CSV row to natural language text.

        This creates a searchable text representation of structured data.

        Args:
            row: CSV row as dictionary

        Returns:
            Natural language text representation
        """
        # For Bulgarian properties data
        if "Название" in row:
            parts = [
                f"Недвижимость: {row.get('Название', '')}",
                f"Город: {row.get('Город', '')}",
                f"Цена: {row.get('Цена (€)', '')} евро",
                f"Комнат: {row.get('Комнат', '')}",
                f"Площадь: {row.get('Площадь (м²)', '')} м²",
                f"Этаж: {row.get('Этаж', '')} из {row.get('Этажей', '')}",
                f"Расстояние до моря: {row.get('До моря (м)', '')} м",
                f"Поддержка: {row.get('Поддержка (€)', '')} евро",
                f"Санузлов: {row.get('Санузлов', '')}",
                f"Мебель: {row.get('Мебель', '')}",
                f"Круглогодичность: {row.get('Круглогодичность', '')}",
                f"Описание: {row.get('Описание', '')}",
            ]
            return ". ".join(part for part in parts if part.split(": ")[-1].strip())

        # Generic fallback - concatenate all fields
        parts = [f"{key}: {value}" for key, value in row.items() if value]
        return ". ".join(parts)

    def create_collection(
        self,
        collection_name: str,
        vector_size: int = 1024,
        recreate: bool = False,
    ) -> None:
        """
        Create Qdrant collection.

        Args:
            collection_name: Name of collection
            vector_size: Embedding dimension (default 1024 for BGE-M3)
            recreate: Whether to drop and recreate if exists
        """
        try:
            self.client.get_collection(collection_name)
            if recreate:
                self.client.delete_collection(collection_name)
                print(f"✓ Deleted existing collection: {collection_name}")
            else:
                print(f"✓ Collection already exists: {collection_name}")
                return
        except Exception:
            pass  # Collection doesn't exist

        # Create collection
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )

        print(f"✓ Created collection: {collection_name}")

    async def index_records(
        self,
        records: list[CSVRecord],
        collection_name: str,
        batch_size: int = 32,
    ) -> dict[str, Any]:
        """
        Index records to Qdrant.

        Args:
            records: List of CSV records
            collection_name: Target collection
            batch_size: Batch size for processing

        Returns:
            Statistics dictionary
        """
        stats = {
            "total_records": len(records),
            "indexed_records": 0,
            "failed_records": 0,
        }

        # Create collection if needed
        self.create_collection(collection_name)

        # Process in batches
        for i in range(0, len(records), batch_size):
            batch = records[i : i + batch_size]
            await self._index_batch(batch, collection_name, stats)

        print("\n✓ Indexing complete:")
        print(f"  - Total: {stats['total_records']}")
        print(f"  - Indexed: {stats['indexed_records']}")
        print(f"  - Failed: {stats['failed_records']}")

        return stats

    async def _index_batch(
        self,
        records: list[CSVRecord],
        collection_name: str,
        stats: dict[str, Any],
    ) -> None:
        """Index a batch of records."""
        try:
            # Extract texts
            texts = [record.text for record in records]

            # Generate embeddings
            embeddings = await self._embed_texts(texts)

            # Prepare points
            points = []
            for record, embedding in zip(records, embeddings):
                point = PointStruct(
                    id=str(uuid.uuid4()),
                    vector=embedding,
                    payload={
                        "text": record.text,
                        "record_id": record.record_id,
                        **record.data,  # Include all CSV fields as metadata
                    },
                )
                points.append(point)

            # Upsert to Qdrant
            self.client.upsert(collection_name=collection_name, points=points)

            stats["indexed_records"] += len(points)
            print(f"  ✓ Indexed batch: {len(points)} records")

        except Exception as e:
            stats["failed_records"] += len(records)
            print(f"  ✗ Failed batch: {e}")

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts using BGE-M3."""
        embeddings = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: self.embedding_model.encode(
                texts,
                batch_size=32,
                show_progress_bar=False,
                normalize_embeddings=True,
            ),
        )
        return embeddings.tolist()


async def main(
    csv_file: str,
    collection_name: str,
    recreate: bool = False,
) -> None:
    """
    Main entry point.

    Args:
        csv_file: Path to CSV file
        collection_name: Qdrant collection name
        recreate: Whether to recreate collection if exists
    """
    print("=" * 60)
    print("CSV to Qdrant Indexer with Docling")
    print("=" * 60)

    # Initialize indexer
    indexer = CSVToQdrantIndexer()

    # Read CSV
    csv_path = Path(csv_file)
    if not csv_path.exists():
        print(f"✗ File not found: {csv_file}")
        return

    records = indexer.read_csv(csv_path)

    # Show sample
    if records:
        print("\nSample record text:")
        print(f"  {records[0].text[:200]}...")

    # Index to Qdrant
    print(f"\nIndexing to collection: {collection_name}")
    await indexer.index_records(
        records=records,
        collection_name=collection_name,
    )

    print("\n" + "=" * 60)
    print("✓ Done!")
    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Index CSV to Qdrant via Docling")
    parser.add_argument("--input", required=True, help="Path to CSV file")
    parser.add_argument(
        "--collection",
        default="csv_data",
        help="Qdrant collection name",
    )
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Recreate collection if exists",
    )

    args = parser.parse_args()

    asyncio.run(
        main(
            csv_file=args.input,
            collection_name=args.collection,
            recreate=args.recreate,
        )
    )
