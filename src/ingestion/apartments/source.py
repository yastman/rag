"""CSV source for apartments with row-level change tracking.

Parses apartments.csv and yields one row per apartment. Change detection uses
a fingerprint of the full observable snapshot (#3371): the canonical
serialized payload plus the hybrid embedding text, so every field that would
change the stored Qdrant point or the rendered card triggers re-embedding.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from src.models.apartment import ApartmentRecord


def record_change_key(record: ApartmentRecord) -> str:
    """Deterministic fingerprint of an apartment's full observable snapshot.

    Hashes the canonical serialized payload (every stored field, including the
    derived description) plus the hybrid embedding text, so any change that
    would alter the stored point changes the key (#3371).
    """
    payload = json.dumps(record.to_payload(), sort_keys=True, ensure_ascii=True, default=str)
    snapshot = f"{payload}\n{record.to_hybrid_description()}"
    return hashlib.sha256(snapshot.encode("utf-8")).hexdigest()[:16]


def parse_apartment_row(row: dict) -> ApartmentRecord:
    """Parse a CSV dict row into an ApartmentRecord."""
    return ApartmentRecord.from_raw(row)


def read_apartments_csv(csv_path: str | Path) -> list[tuple[str, str, ApartmentRecord]]:
    """Read CSV and return (unique_key, change_key, record) tuples.

    unique_key: deterministic row identity (complex::section::apt_number)
    change_key: fingerprint of the full observable snapshot (triggers
        re-embedding when changed)
    """
    results: list[tuple[str, str, ApartmentRecord]] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = parse_apartment_row(row)
            unique_key = f"{record.complex_name}::{record.section}::{record.apartment_number}"
            change = record_change_key(record)
            results.append((unique_key, change, record))
    return results
