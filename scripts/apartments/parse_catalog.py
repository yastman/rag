"""Parse apartment catalog text into structured CSV data.

Input format (pipe-separated rows grouped under complex name headers):

    Complex Name
    SECTION | APT_NUM | ROOMS | FLOOR_LABEL | AREA_M2 | VIEW_RAW |
    PRICE_EUR | PRICE_BGN | FURNISHED | FLOOR_PLAN | PHOTO | OLD_PRICE

    Where OLD_PRICE is "-" for no promotion, or a number for old price.

Usage:
    python scripts/apartments/parse_catalog.py input.txt data/apartments.csv
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path


CSV_COLUMNS = [
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


def _parse_bool_field(val: str) -> str:
    """Normalize yes/no/true/false strings to 'True'/'False'."""
    v = val.strip().lower()
    if v in {"yes", "y", "true", "1", "да"}:
        return "True"
    return "False"


def parse_catalog_text(text: str) -> list[dict]:
    """Parse catalog text format into list of apartment dicts.

    Blank lines and section headers (lines without '|') are handled.
    """
    records: list[dict] = []
    current_complex: str = ""

    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        # Lines without '|' are complex name headers
        if "|" not in line:
            current_complex = line
            continue

        # Apartment row: split on '|'
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 11:
            continue

        section = parts[0]
        apartment_number = parts[1]
        rooms = parts[2]
        floor_label = parts[3]
        area_m2 = parts[4]
        view_raw = parts[5]
        price_eur = parts[6]
        price_bgn = parts[7]
        is_furnished = _parse_bool_field(parts[8])
        has_floor_plan = _parse_bool_field(parts[9])
        has_photo = _parse_bool_field(parts[10])

        # Promotion: column 11 is old_price ("-" = no promotion)
        old_price_raw = parts[11].strip() if len(parts) > 11 else "-"
        if old_price_raw == "-" or not old_price_raw:
            is_promotion = "False"
            old_price_eur = ""
        else:
            is_promotion = "True"
            old_price_eur = old_price_raw

        records.append(
            {
                "complex_name": current_complex,
                "section": section,
                "apartment_number": apartment_number,
                "rooms": rooms,
                "floor_label": floor_label,
                "area_m2": area_m2,
                "view_raw": view_raw,
                "price_eur": price_eur,
                "price_bgn": price_bgn,
                "is_furnished": is_furnished,
                "has_floor_plan": has_floor_plan,
                "has_photo": has_photo,
                "is_promotion": is_promotion,
                "old_price_eur": old_price_eur,
            }
        )

    return records


def write_csv(records: list[dict], output_path: str) -> None:
    """Write records to CSV file with standard columns."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python parse_catalog.py <input_text_file> <output_csv>")
        sys.exit(1)

    input_text = Path(sys.argv[1]).read_text(encoding="utf-8")
    parsed = parse_catalog_text(input_text)
    write_csv(parsed, sys.argv[2])
    print(f"Wrote {len(parsed)} records to {sys.argv[2]}")
