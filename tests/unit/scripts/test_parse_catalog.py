"""Tests for parse_catalog script (TDD — RED first)."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Sample catalog text: 2 records from Messambria Fort Beach, 1 from Premier
# Format: complex header, then pipe-separated rows
# Columns: section | apt_num | rooms | floor_label | area_m2 | view_raw |
#          price_eur | price_bgn | furnished | floor_plan | photo | old_price
# old_price "-" → not on promotion; a number → is_promotion=True
# ---------------------------------------------------------------------------

SAMPLE_TEXT = """\
Messambria Fort Beach
A-1 | 88 | 2 | 3 | 76.4 | pool/sea | 185000 | 361675.5 | yes | yes | no | -
B-2 | 174 | 1 | gr. | 40.0 | garden | 82000 | 160299.1 | no | yes | yes | 90000

Premier Fort Beach
D-1 | 248 | 2 | 4 | 78.66 | sea | 215000 | 420503.45 | yes | yes | yes | -
"""


class TestParseCatalogText:
    """Tests for parse_catalog_text() function."""

    def test_parses_correct_count(self) -> None:
        from scripts.apartments.parse_catalog import parse_catalog_text

        records = parse_catalog_text(SAMPLE_TEXT)
        assert len(records) == 3

    def test_first_record_fields(self) -> None:
        from scripts.apartments.parse_catalog import parse_catalog_text

        records = parse_catalog_text(SAMPLE_TEXT)
        r = records[0]
        assert r["complex_name"] == "Messambria Fort Beach"
        assert r["section"] == "A-1"
        assert r["apartment_number"] == "88"
        assert r["rooms"] == "2"
        assert r["floor_label"] == "3"
        assert float(r["area_m2"]) == pytest.approx(76.4)
        assert r["view_raw"] == "pool/sea"
        assert float(r["price_eur"]) == pytest.approx(185000.0)

    def test_furnished_detection(self) -> None:
        from scripts.apartments.parse_catalog import parse_catalog_text

        records = parse_catalog_text(SAMPLE_TEXT)
        assert records[0]["is_furnished"] == "True"  # yes → True
        assert records[1]["is_furnished"] == "False"  # no → False

    def test_photo_detection(self) -> None:
        from scripts.apartments.parse_catalog import parse_catalog_text

        records = parse_catalog_text(SAMPLE_TEXT)
        assert records[0]["has_photo"] == "False"  # no
        assert records[1]["has_photo"] == "True"  # yes

    def test_ground_floor_label(self) -> None:
        from scripts.apartments.parse_catalog import parse_catalog_text

        records = parse_catalog_text(SAMPLE_TEXT)
        assert records[1]["floor_label"] == "gr."

    def test_promotion_detection(self) -> None:
        from scripts.apartments.parse_catalog import parse_catalog_text

        records = parse_catalog_text(SAMPLE_TEXT)
        # B-2 has old_price=90000 → promotion
        assert records[1]["is_promotion"] == "True"
        assert float(records[1]["old_price_eur"]) == pytest.approx(90000.0)
        # A-1 has old_price=- → no promotion
        assert records[0]["is_promotion"] == "False"
        assert records[0]["old_price_eur"] == ""

    def test_complex_name_inherited(self) -> None:
        from scripts.apartments.parse_catalog import parse_catalog_text

        records = parse_catalog_text(SAMPLE_TEXT)
        assert records[2]["complex_name"] == "Premier Fort Beach"


class TestWriteCsv:
    """Tests for write_csv() function."""

    def test_writes_csv_with_correct_row_count(self, tmp_path: Path) -> None:
        from scripts.apartments.parse_catalog import parse_catalog_text, write_csv

        records = parse_catalog_text(SAMPLE_TEXT)
        output = tmp_path / "out.csv"
        write_csv(records, str(output))

        text = output.read_text()
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert len(rows) == 3

    def test_csv_has_promotion_columns(self, tmp_path: Path) -> None:
        from scripts.apartments.parse_catalog import parse_catalog_text, write_csv

        records = parse_catalog_text(SAMPLE_TEXT)
        output = tmp_path / "out.csv"
        write_csv(records, str(output))

        text = output.read_text()
        reader = csv.DictReader(io.StringIO(text))
        list(reader)  # consume rows
        assert "is_promotion" in (reader.fieldnames or [])
        assert "old_price_eur" in (reader.fieldnames or [])

    def test_csv_columns_constant_has_promotions(self) -> None:
        from scripts.apartments.parse_catalog import CSV_COLUMNS

        assert "is_promotion" in CSV_COLUMNS
        assert "old_price_eur" in CSV_COLUMNS
