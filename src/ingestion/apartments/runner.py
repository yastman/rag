"""Incremental apartment ingestion runner.

Tracks row-level changes via SHA-256 hash of mutable fields. Only re-embeds
and upserts rows that changed since last run. State persisted to JSON file.

Usage:
    # Full re-index (first run or force)
    python -m src.ingestion.apartments.runner

    # Incremental (only changed rows)
    python -m src.ingestion.apartments.runner --incremental

    # Dry run (show what would change)
    python -m src.ingestion.apartments.runner --incremental --dry-run
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from src.ingestion.apartments.flow import (
    COLLECTION,
    build_ingestion_batch,
    format_apartment_text,
)
from src.ingestion.apartments.source import read_apartments_csv


if TYPE_CHECKING:
    from telegram_bot.services.apartment_models import ApartmentRecord


logger = logging.getLogger(__name__)


class IncrementalApartmentIngester:
    """Apartment ingestion with row-level change tracking."""

    def __init__(
        self,
        csv_path: str = "data/apartments.csv",
        qdrant_url: str = "http://localhost:6333",
        bge_url: str = "http://localhost:8000",
        state_path: str = ".apartments_ingestion_state.json",
    ) -> None:
        self.csv_path = csv_path
        self.qdrant_url = qdrant_url
        self.bge_url = bge_url
        self.state_path = state_path
        self._state: dict[str, str] = {}  # unique_key -> change_key

    def _load_state(self) -> dict[str, str]:
        """Load previous ingestion state from JSON file."""
        path = Path(self.state_path)
        if path.exists():
            return json.loads(path.read_text())
        return {}

    def _save_state(self, state: dict[str, str]) -> None:
        """Save current ingestion state to JSON file."""
        Path(self.state_path).write_text(json.dumps(state, indent=2))

    def run_incremental(self, dry_run: bool = False) -> dict:
        """Run incremental ingestion. Returns stats dict."""
        rows = read_apartments_csv(self.csv_path)
        prev_state = self._load_state()

        changed: list[ApartmentRecord] = []
        new_state: dict[str, str] = {}

        for unique_key, change_key, record in rows:
            new_state[unique_key] = change_key
            if prev_state.get(unique_key) != change_key:
                changed.append(record)

        stats = {
            "total": len(rows),
            "changed": len(changed),
            "unchanged": len(rows) - len(changed),
        }

        logger.info(
            "Incremental scan: %d total, %d changed, %d unchanged",
            stats["total"],
            stats["changed"],
            stats["unchanged"],
        )

        if changed and not dry_run:
            self._embed_and_upsert(changed)

        # Always save state (even dry_run — to track what was seen)
        self._save_state(new_state)

        return stats

    def _embed_and_upsert(self, records: list[ApartmentRecord]) -> None:
        """Embed changed records and upsert to Qdrant."""
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        from telegram_bot.services.bge_m3_client import BGEM3SyncClient

        bge = BGEM3SyncClient(base_url=self.bge_url)
        client = QdrantClient(url=self.qdrant_url)

        descriptions = [format_apartment_text(r) for r in records]

        # Embed
        dense_result = bge.encode_dense(descriptions)
        sparse_result = bge.encode_sparse(descriptions)
        colbert_result = bge.encode_colbert(descriptions)

        # Build points
        point_dicts = build_ingestion_batch(
            records,
            dense_result.vectors,
            sparse_result.weights,
            colbert_result.colbert_vecs,
        )

        # Upsert
        points = [
            PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"]) for p in point_dicts
        ]
        for i in range(0, len(points), 100):
            batch = points[i : i + 100]
            client.upsert(collection_name=COLLECTION, points=batch)
            logger.info("Upserted %d/%d", min(i + 100, len(points)), len(points))

        bge.close()
        logger.info("Done. %d apartments upserted.", len(points))


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    parser = argparse.ArgumentParser(description="Incremental apartment ingestion")
    parser.add_argument("--incremental", action="store_true", help="Only re-embed changed rows")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without upserting")
    args = parser.parse_args()

    ingester = IncrementalApartmentIngester(
        csv_path=os.getenv("APARTMENTS_CSV", "data/apartments.csv"),
        qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        bge_url=os.getenv("BGE_M3_URL", "http://localhost:8000"),
    )

    if args.incremental:
        stats = ingester.run_incremental(dry_run=args.dry_run)
        print(f"Stats: {stats}")
    else:
        # Full re-index: clear state and run
        Path(ingester.state_path).unlink(missing_ok=True)
        stats = ingester.run_incremental(dry_run=args.dry_run)
        print(f"Full re-index stats: {stats}")
