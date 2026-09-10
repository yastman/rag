"""Tests for incremental apartment ingestion runner."""

import csv
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.ingestion.apartments.runner import IncrementalApartmentIngester
from src.runtime.qdrant.contracts import APARTMENTS_COLLECTION
from src.services.bge_m3_client import HybridResult


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


class TestHybridEncoding:
    """Regression guard: ingestion MUST use encode_hybrid, not 3 separate calls."""

    def test_embed_uses_single_hybrid_call(self, tmp_path: Path) -> None:
        """Runner calls encode_hybrid() once, never encode_dense/sparse/colbert."""
        csv_path = tmp_path / "apt.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            qdrant_url="http://localhost:6333",
            bge_url="http://localhost:8000",
            state_path=str(tmp_path / ".state.json"),
        )

        with (
            patch("src.services.bge_m3_client.BGEM3SyncClient") as MockBGE,
            patch("qdrant_client.QdrantClient"),
            patch("src.ingestion.apartments.runner.build_ingestion_batch", return_value=[]),
        ):
            mock_bge = MockBGE.return_value
            mock_bge.encode_hybrid.return_value = HybridResult(
                dense_vecs=[[0.1] * 1024],
                lexical_weights=[{"indices": [1], "values": [0.5]}],
                colbert_vecs=[[[0.1] * 1024] * 5],
            )

            ingester.run_incremental(force_full=True)

            mock_bge.encode_hybrid.assert_called_once()
            mock_bge.encode_dense.assert_not_called()
            mock_bge.encode_sparse.assert_not_called()
            mock_bge.encode_colbert.assert_not_called()


# ---------------------------------------------------------------------------
# Collection and credential propagation (#3460)
# ---------------------------------------------------------------------------


SELECTED_COLLECTION = "audit_3460_apartments"
SELECTED_API_KEY = "test-api-key-3460"


def _hybrid_for_row_count(rows: int) -> HybridResult:
    return HybridResult(
        dense_vecs=[[0.1] * 1024] * rows,
        lexical_weights=[{"indices": [1], "values": [0.5]}] * rows,
        colbert_vecs=[[[0.1] * 1024] * 5] * rows,
    )


class TestCollectionAndCredentialPropagation:
    """#3460: the selected collection and supplied API key must reach every
    Qdrant client and every delete/upsert call — never a literal fallback."""

    def _ingester(self, tmp_path: Path, **overrides) -> IncrementalApartmentIngester:
        csv_path = tmp_path / "apt.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        defaults: dict = {
            "csv_path": str(csv_path),
            "qdrant_url": "https://qdrant.example",
            "qdrant_api_key": SELECTED_API_KEY,
            "collection_name": SELECTED_COLLECTION,
            "state_path": str(tmp_path / ".state.json"),
        }
        defaults.update(overrides)
        return IncrementalApartmentIngester(**defaults)

    def test_init_stores_collection_name_and_api_key(self, tmp_path: Path) -> None:
        ingester = self._ingester(tmp_path)

        assert ingester.collection_name == SELECTED_COLLECTION
        assert ingester.qdrant_api_key == SELECTED_API_KEY

    def test_default_collection_is_canonical_default(self, tmp_path: Path) -> None:
        """Standalone runner without an override keeps the canonical collection."""
        ingester = self._ingester(tmp_path, collection_name=None, qdrant_api_key=None)

        assert ingester.collection_name == APARTMENTS_COLLECTION
        assert ingester.qdrant_api_key is None

    def test_upsert_targets_selected_collection_with_supplied_api_key(self, tmp_path: Path) -> None:
        ingester = self._ingester(tmp_path)

        with (
            patch("src.services.bge_m3_client.BGEM3SyncClient") as MockBGE,
            patch("qdrant_client.QdrantClient") as MockQdrant,
        ):
            MockBGE.return_value.encode_hybrid.return_value = _hybrid_for_row_count(1)
            ingester.run_incremental(force_full=True)

        # Authenticated client construction — protected HTTPS endpoints.
        MockQdrant.assert_called_once_with(url="https://qdrant.example", api_key=SELECTED_API_KEY)
        client = MockQdrant.return_value
        assert client.upsert.call_count >= 1
        for call in client.upsert.call_args_list:
            assert call.kwargs["collection_name"] == SELECTED_COLLECTION
            assert call.kwargs["wait"] is True
        client.close.assert_called_once()

    def test_delete_targets_selected_collection_with_supplied_api_key(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apt.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        state_path = tmp_path / ".state.json"
        state_path.write_text(json.dumps({"Gone Complex::B-2::999": "deadhash"}), encoding="utf-8")
        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            qdrant_url="https://qdrant.example",
            qdrant_api_key=SELECTED_API_KEY,
            collection_name=SELECTED_COLLECTION,
            state_path=str(state_path),
        )

        with (
            patch.object(ingester, "_embed_and_upsert"),
            patch("qdrant_client.QdrantClient") as MockQdrant,
        ):
            stats = ingester.run_incremental()

        MockQdrant.assert_called_once_with(url="https://qdrant.example", api_key=SELECTED_API_KEY)
        client = MockQdrant.return_value
        delete_kwargs = client.delete.call_args.kwargs
        assert delete_kwargs["collection_name"] == SELECTED_COLLECTION
        assert delete_kwargs["wait"] is True
        client.close.assert_called_once()
        assert stats["removed"] == 1

    def test_upsert_client_closed_when_upsert_fails(self, tmp_path: Path) -> None:
        """Sync Qdrant clients are explicitly closed on failure too."""
        ingester = self._ingester(tmp_path)

        with (
            patch("src.services.bge_m3_client.BGEM3SyncClient") as MockBGE,
            patch("qdrant_client.QdrantClient") as MockQdrant,
            pytest.raises(RuntimeError, match="upsert boom"),
        ):
            MockBGE.return_value.encode_hybrid.return_value = _hybrid_for_row_count(1)
            MockQdrant.return_value.upsert.side_effect = RuntimeError("upsert boom")
            ingester.run_incremental(force_full=True)

        MockQdrant.return_value.close.assert_called_once()

    def test_delete_client_closed_when_delete_fails(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apt.csv"
        _write_csv([SAMPLE_ROW], csv_path)
        state_path = tmp_path / ".state.json"
        state_path.write_text(json.dumps({"Gone Complex::B-2::999": "deadhash"}), encoding="utf-8")
        ingester = IncrementalApartmentIngester(
            csv_path=str(csv_path),
            qdrant_api_key=SELECTED_API_KEY,
            collection_name=SELECTED_COLLECTION,
            state_path=str(state_path),
        )

        with (
            patch.object(ingester, "_embed_and_upsert"),
            patch("qdrant_client.QdrantClient") as MockQdrant,
            pytest.raises(RuntimeError, match="delete boom"),
        ):
            MockQdrant.return_value.delete.side_effect = RuntimeError("delete boom")
            ingester.run_incremental()

        MockQdrant.return_value.close.assert_called_once()
