"""CocoIndex-compatible CSV source for apartments with row-level change tracking.

Parses apartments.csv and yields one row per apartment. Change detection uses
a hash of mutable fields (price, area, furnished, promotion, view) so only
modified rows trigger re-embedding.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

from telegram_bot.services.apartment_models import ApartmentRecord


# Mutable fields — changes in these trigger re-embedding
_CHANGE_FIELDS = ("price_eur", "area_m2", "is_furnished", "is_promotion", "view_raw", "city")


def row_change_key(row: dict) -> str:
    """Deterministic hash of mutable fields for change detection."""
    parts = "|".join(str(row.get(f, "")) for f in _CHANGE_FIELDS)
    return hashlib.sha256(parts.encode()).hexdigest()[:16]


def parse_apartment_row(row: dict) -> ApartmentRecord:
    """Parse a CSV dict row into an ApartmentRecord."""
    return ApartmentRecord.from_raw(row)


def read_apartments_csv(csv_path: str | Path) -> list[tuple[str, str, ApartmentRecord]]:
    """Read CSV and return (unique_key, change_key, record) tuples.

    unique_key: deterministic row identity (complex::section::apt_number)
    change_key: hash of mutable fields (triggers re-embedding when changed)
    """
    results: list[tuple[str, str, ApartmentRecord]] = []
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = parse_apartment_row(row)
            unique_key = f"{record.complex_name}::{record.section}::{record.apartment_number}"
            change = row_change_key(row)
            results.append((unique_key, change, record))
    return results
