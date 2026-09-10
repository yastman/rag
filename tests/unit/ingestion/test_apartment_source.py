"""Tests for apartment CSV source."""

import csv
from pathlib import Path

import pytest

from src.ingestion.apartments.source import (
    parse_apartment_row,
    read_apartments_csv,
    record_change_key,
)


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
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


BASE_ROW = {
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


class TestParseApartmentRow:
    def test_basic_row(self) -> None:
        record = parse_apartment_row(dict(BASE_ROW))
        assert record.complex_name == "Premier Fort Beach"
        assert record.city == "Солнечный берег"
        assert record.rooms == 2
        assert record.price_eur == 215000.0

    def test_ground_floor(self) -> None:
        row = {**BASE_ROW, "complex_name": "Test", "apartment_number": "1", "floor_label": "gr."}
        record = parse_apartment_row(row)
        assert record.floor == 0


class TestRecordChangeKey:
    """#3371: the fingerprint must cover the full observable snapshot — every
    field that changes the stored payload or the embedding text must change
    the key, so an incremental run re-embeds the row."""

    @staticmethod
    def _key(**overrides: str) -> str:
        return record_change_key(parse_apartment_row({**BASE_ROW, **overrides}))

    def test_identical_rows_produce_identical_keys(self) -> None:
        assert self._key() == self._key()

    @pytest.mark.parametrize(
        ("field", "changed_value"),
        [
            ("city", "Свети Влас"),
            ("rooms", "3"),
            ("floor_label", "7"),
            ("area_m2", "99.5"),
            ("view_raw", "pool"),
            ("price_eur", "230000"),
            ("price_bgn", "450000"),
            ("is_furnished", "True"),
            ("has_floor_plan", "True"),
            ("has_photo", "True"),
            ("is_promotion", "True"),
            ("old_price_eur", "225000"),
        ],
    )
    def test_field_change_changes_key(self, field: str, changed_value: str) -> None:
        assert self._key() != self._key(**{field: changed_value})


class TestReadApartmentsCsv:
    def test_reads_300_row_cyrillic_fixture_as_utf8(self, tmp_path: Path) -> None:
        """#3371: a 300-row Cyrillic CSV must round-trip on Windows, where the
        default open() encoding is a legacy locale codec instead of UTF-8."""
        rows = [
            {
                **BASE_ROW,
                "apartment_number": str(number),
                "complex_name": "Морской Дворик",
            }
            for number in range(1, 301)
        ]
        csv_path = tmp_path / "apartments.csv"
        _write_csv(rows, csv_path)

        results = read_apartments_csv(csv_path)

        assert len(results) == 300
        for unique_key, _change_key, record in results:
            assert record.complex_name == "Морской Дворик"
            assert record.city == "Солнечный берег"
            assert unique_key.startswith("Морской Дворик::D-1::")
        assert len({change_key for _, change_key, _ in results}) == 300

    def test_same_content_across_reads_keeps_key_stable(self, tmp_path: Path) -> None:
        csv_path = tmp_path / "apartments.csv"
        _write_csv([dict(BASE_ROW)], csv_path)

        first = read_apartments_csv(csv_path)
        second = read_apartments_csv(csv_path)

        assert first[0][0] == second[0][0]
        assert first[0][1] == second[0][1]
