"""Tests for incremental apartment ingestion runner."""

import csv
from pathlib import Path
from unittest.mock import patch

from src.ingestion.apartments.runner import IncrementalApartmentIngester


def _write_csv(rows: list[dict], path: Path) -> None:
    fieldnames = [
        "complex_name",
        "section",
        "apartment_number",
        "rooms",
        "floor_label",
        "area_m2",
        "view_raw",
        "price_eur",
        "price_bgn",
        "is_furnished",
        "has_floor_plan",
        "has_photo",
        "is_promotion",
        "old_price_eur",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


SAMPLE_ROW = {
    "complex_name": "Test Complex",
    "section": "A-1",
    "apartment_number": "101",
    "rooms": "2",
    "floor_label": "3",
    "area_m2": "65.0",
    "view_raw": "sea",
    "price_eur": "120000",
    "price_bgn": "234000",
    "is_furnished": "False",
    "has_floor_plan": "False",
    "has_photo": "False",
    "is_promotion": "False",
    "old_price_eur": "",
}


class TestIncrementalIngester:
    def test_first_run_ingests_all(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([SAMPLE_ROW], csv_path)

        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            qdrant_url="http://localhost:6333",
            bge_url="http://localhost:8000",
            state_path=str(tmp_path / ".ingestion_state.json"),
        )

        with patch.object(ingester, "_embed_and_upsert"):
            stats = ingester.run_incremental(dry_run=True)

        assert stats["total"] == 1
        assert stats["changed"] == 1
        assert stats["unchanged"] == 0

    def test_dry_run_does_not_persist_state(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        state_path = tmp_path / ".ingestion_state.json"

        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            state_path=str(state_path),
        )

        stats_first = ingester.run_incremental(dry_run=True)
        stats_second = ingester.run_incremental(dry_run=True)

        assert stats_first["changed"] == 1
        assert stats_second["changed"] == 1
        assert not state_path.exists()

    def test_second_run_skips_unchanged(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        state_path = tmp_path / ".ingestion_state.json"

        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            qdrant_url="http://localhost:6333",
            bge_url="http://localhost:8000",
            state_path=str(state_path),
        )

        # First run — ingests and saves state
        with patch.object(ingester, "_embed_and_upsert"):
            ingester.run_incremental(dry_run=False)

        # Second run — same data, nothing changed
        with patch.object(ingester, "_embed_and_upsert") as mock_embed:
            stats = ingester.run_incremental(dry_run=False)

        mock_embed.assert_not_called()
        assert stats["changed"] == 0
        assert stats["unchanged"] == 1

    def test_price_change_triggers_reindex(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        state_path = tmp_path / ".ingestion_state.json"

        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            qdrant_url="http://localhost:6333",
            bge_url="http://localhost:8000",
            state_path=str(state_path),
        )

        # First run
        with patch.object(ingester, "_embed_and_upsert"):
            ingester.run_incremental(dry_run=False)

        # Change price
        changed_row = {**SAMPLE_ROW, "price_eur": "130000"}
        _write_csv([changed_row], csv_path)

        with patch.object(ingester, "_embed_and_upsert") as mock_embed:
            stats = ingester.run_incremental(dry_run=False)

        mock_embed.assert_called_once()
        assert stats["changed"] == 1

    def test_removed_row_triggers_delete(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        state_path = tmp_path / ".ingestion_state.json"

        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            state_path=str(state_path),
        )

        with (
            patch.object(ingester, "_embed_and_upsert"),
            patch.object(ingester, "_delete_removed_points") as delete_mock,
        ):
            ingester.run_incremental(dry_run=False)
        delete_mock.assert_not_called()

        _write_csv([], csv_path)

        with (
            patch.object(ingester, "_embed_and_upsert"),
            patch.object(ingester, "_delete_removed_points") as delete_mock,
        ):
            stats = ingester.run_incremental(dry_run=False)

        delete_mock.assert_called_once()
        assert stats["removed"] == 1

    def test_force_full_dry_run_keeps_existing_state_file(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        state_path = tmp_path / ".ingestion_state.json"
        original_state = {"legacy::row::1": "oldhash"}
        state_path.write_text('{"legacy::row::1": "oldhash"}', encoding="utf-8")

        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            state_path=str(state_path),
        )

        stats = ingester.run_incremental(dry_run=True, force_full=True)

        assert stats["changed"] == 1
        assert stats["removed"] == 0
        assert state_path.exists()
        assert ingester._load_state() == original_state
