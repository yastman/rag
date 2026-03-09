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
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from src.ingestion.apartments.flow import (
    COLLECTION,
    build_ingestion_batch,
    format_apartment_text,
    generate_point_id,
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

    def _load_state(self) -> dict[str, str]:
        """Load previous ingestion state from JSON file."""
        path = Path(self.state_path)
        if path.exists():
            raw_state = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw_state, dict):
                return {str(k): str(v) for k, v in raw_state.items()}
            logger.warning("State file has invalid format; ignoring: %s", self.state_path)
        return {}

    def _save_state(self, state: dict[str, str]) -> None:
        """Save current ingestion state to JSON file."""
        path = Path(self.state_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def run_incremental(self, dry_run: bool = False, *, force_full: bool = False) -> dict:
        """Run ingestion and return stats.

        By default, compares against persisted state (incremental mode).
        When ``force_full`` is True, treats all rows as changed without mutating
        state in dry-run mode.
        """
        rows = read_apartments_csv(self.csv_path)
        prev_state = {} if force_full else self._load_state()

        changed: list[ApartmentRecord] = []
        new_state: dict[str, str] = {}

        for unique_key, change_key, record in rows:
            new_state[unique_key] = change_key
            if prev_state.get(unique_key) != change_key:
                changed.append(record)

        removed_keys = set(prev_state) - set(new_state)

        stats = {
            "total": len(rows),
            "changed": len(changed),
            "unchanged": len(rows) - len(changed),
            "removed": len(removed_keys),
        }

        mode = "full" if force_full else "incremental"
        logger.info(
            "%s scan: %d total, %d changed, %d unchanged, %d removed",
            mode.capitalize(),
            stats["total"],
            stats["changed"],
            stats["unchanged"],
            stats["removed"],
        )

        if dry_run:
            logger.info("Dry-run mode: skipping upsert/delete and state update")
            return stats

        if changed:
            self._embed_and_upsert(changed)
        if removed_keys:
            self._delete_removed_points(removed_keys)
        self._save_state(new_state)

        return stats

    def _delete_removed_points(self, removed_unique_keys: set[str]) -> int:
        """Delete points for apartments removed from CSV source."""
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointIdsList

        point_ids: list[int | str | uuid.UUID] = []
        for unique_key in removed_unique_keys:
            try:
                complex_name, section, apartment_number = unique_key.split("::", maxsplit=2)
            except ValueError:
                logger.warning("Skipping malformed state key: %s", unique_key)
                continue
            point_ids.append(generate_point_id(complex_name, section, apartment_number))

        if not point_ids:
            return 0

        client = QdrantClient(url=self.qdrant_url)
        client.delete(
            collection_name=COLLECTION,
            points_selector=PointIdsList(points=point_ids),
            wait=True,
        )
        logger.info("Deleted %d removed apartments from Qdrant.", len(point_ids))
        return len(point_ids)

    def _embed_and_upsert(self, records: list[ApartmentRecord]) -> None:
        """Embed changed records and upsert to Qdrant."""
        from qdrant_client import QdrantClient
        from qdrant_client.models import PointStruct

        from telegram_bot.services.bge_m3_client import BGEM3SyncClient

        if not records:
            return

        bge = BGEM3SyncClient(base_url=self.bge_url)
        client = QdrantClient(url=self.qdrant_url)
        try:
            descriptions = [format_apartment_text(r) for r in records]

            # Embed — single hybrid call (3x fewer HTTP requests, 1 model forward pass)
            hybrid_result = bge.encode_hybrid(descriptions)

            # Build points
            point_dicts = build_ingestion_batch(
                records,
                hybrid_result.dense_vecs,
                hybrid_result.lexical_weights,
                hybrid_result.colbert_vecs or [],
            )

            # Upsert
            points = [
                PointStruct(id=p["id"], vector=p["vector"], payload=p["payload"])
                for p in point_dicts
            ]
            for i in range(0, len(points), 20):
                batch = points[i : i + 20]
                client.upsert(collection_name=COLLECTION, points=batch, wait=True)
                logger.info("Upserted %d/%d", min(i + 20, len(points)), len(points))

            logger.info("Done. %d apartments upserted.", len(points))
        finally:
            bge.close()


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
        stats = ingester.run_incremental(dry_run=args.dry_run, force_full=True)
        print(f"Full re-index stats: {stats}")
