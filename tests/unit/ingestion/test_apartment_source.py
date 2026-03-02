"""Tests for CocoIndex apartment CSV source."""

import csv
from pathlib import Path

from src.ingestion.apartments.source import parse_apartment_row, row_change_key


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
        "city",
    ]
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


class TestParseApartmentRow:
    def test_basic_row(self) -> None:
        row = {
            "complex_name": "Premier Fort Beach",
            "section": "D-1",
            "apartment_number": "248",
            "rooms": "2",
            "floor_label": "4",
            "area_m2": "78.66",
            "view_raw": "sea",
            "price_eur": "215000.00",
            "price_bgn": "420503.45",
            "is_furnished": "False",
            "has_floor_plan": "False",
            "has_photo": "False",
            "is_promotion": "False",
            "old_price_eur": "",
            "city": "Солнечный берег",
        }
        record = parse_apartment_row(row)
        assert record.complex_name == "Premier Fort Beach"
        assert record.city == "Солнечный берег"
        assert record.rooms == 2
        assert record.price_eur == 215000.0

    def test_ground_floor(self) -> None:
        row = {
            "complex_name": "Test",
            "section": "A",
            "apartment_number": "1",
            "rooms": "1",
            "floor_label": "gr.",
            "area_m2": "30",
            "view_raw": "",
            "price_eur": "50000",
            "price_bgn": "97000",
            "is_furnished": "False",
            "has_floor_plan": "False",
            "has_photo": "False",
            "is_promotion": "False",
            "old_price_eur": "",
        }
        record = parse_apartment_row(row)
        assert record.floor == 0


class TestRowChangeKey:
    def test_same_data_same_key(self) -> None:
        row = {
            "price_eur": "100000",
            "area_m2": "50",
            "is_furnished": "False",
            "is_promotion": "False",
            "view_raw": "sea",
        }
        assert row_change_key(row) == row_change_key(row)

    def test_price_change_different_key(self) -> None:
        row1 = {
            "price_eur": "100000",
            "area_m2": "50",
            "is_furnished": "False",
            "is_promotion": "False",
            "view_raw": "sea",
        }
        row2 = {**row1, "price_eur": "110000"}
        assert row_change_key(row1) != row_change_key(row2)
