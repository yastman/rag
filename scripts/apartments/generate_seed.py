#!/usr/bin/env python3
"""Generate the synthetic demo apartment seed (data/apartments.csv).

Issue #3203: the tracked seed must be deterministic, synthetic, PII-free, and
mutually truthful with the visible demo prompts. This script is the single
provenance of ``data/apartments.csv``:

    uv run python scripts/apartments/generate_seed.py           # (re)write seed
    uv run python scripts/apartments/generate_seed.py --check   # verify only

Determinism: the layout is a pure function of a fixed RNG seed (3203) and the
canonical demo domain in ``src/runtime/domain_defaults.py``. Re-running the
generator always produces byte-identical output (enforced by ``--check``).

Golden-query guarantees baked into the layout (see domain_defaults.py):
- "Студия в Солнечном берегу до 100 000€"  → rooms=1 in Солнечный берег ≤ 100k
- "Двушка в Premier Fort Beach"            → rooms=3 in Premier Fort Beach
- "Трёшка в Элените до 200 000€"           → rooms=4 in Элените ≤ 200k
- "Апартамент в Свети Влас от 150 000€"    → any rooms in Свети Влас ≥ 150k
- "Трёшка в Свети Власе до 60 000€"        → deliberately ZERO rows
  (rooms=4 in Свети Влас always costs more, exercising the empty-state copy)

All names, numbers, prices, and areas are fabricated. No real personal data.
"""

from __future__ import annotations

import argparse
import csv
import io
import random
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.runtime.domain_defaults import DEMO_CITIES, DEMO_COMPLEX_CITIES


DEFAULT_CSV_PATH = Path("data/apartments.csv")

CSV_COLUMNS = [
    "complex_name",
    "city",
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

BGN_PER_EUR = 1.95583
RNG_SEED = 3203
LISTINGS_PER_COMPLEX = 30

# Room mix per complex: total rooms (1=studio ... 5=four-bedroom), 30 total.
_ROOM_MIX: list[int] = [1] * 8 + [2] * 8 + [3] * 6 + [4] * 5 + [5] * 3

# Synthetic price bands (EUR) per total rooms. Bounds are hard clamps applied
# after view premiums so no row escapes its band.
_PRICE_RANGE: dict[int, tuple[int, int]] = {
    1: (55_000, 95_000),
    2: (70_000, 120_000),
    3: (90_000, 160_000),
    4: (115_000, 215_000),
    5: (145_000, 255_000),
}

# City-specific overrides that encode the golden/no-result guarantees above.
_PRICE_RANGE_OVERRIDES: dict[tuple[str, int], tuple[int, int]] = {
    # Golden: "Трёшка в Элените до 200 000€" → all Элените rooms=4 stay ≤ 195k.
    ("Элените", 4): (115_000, 195_000),
    # No-result: "Трёшка в Свети Власе до 60 000€" → rooms=4 in Свети Влас
    # never drops near 60k.
    ("Свети Влас", 4): (135_000, 215_000),
    # Golden: "Апартамент в Свети Влас от 150 000€" → rooms=5 there ≥ 155k.
    ("Свети Влас", 5): (155_000, 250_000),
}

# Synthetic area ranges (m²) per total rooms.
_AREA_RANGE: dict[int, tuple[float, float]] = {
    1: (32.0, 42.0),
    2: (48.0, 68.0),
    3: (66.0, 92.0),
    4: (88.0, 122.0),
    5: (110.0, 150.0),
}

# View vocabulary understood by src/models/apartment.py::normalize_view and
# fully covered by the filter-dialog VIEW_DISPLAY options.
_VIEWS: list[str] = [
    "sea",
    "sea panorama",
    "ultra sea panorama",
    "ultra sea",
    "pool",
    "garden",
    "forest",
    "sea/pool",
    "garden/sea",
    "pool/garden",
]

# Price premium per primary view tag.
_VIEW_PREMIUM: dict[str, float] = {
    "ultra_sea_panorama": 0.15,
    "sea_panorama": 0.10,
    "ultra_sea": 0.10,
    "sea": 0.05,
    "pool": 0.03,
    "garden": 0.0,
    "forest": -0.02,
}

_SECTIONS: list[str] = ["A", "B", "C"]


def _clamp_band(price: int, band: tuple[int, int]) -> int:
    return min(max(price, band[0]), band[1])


def _round_to_step(value: float, step: int) -> int:
    return int(round(value / step) * step)


def _view_premium(view_raw: str) -> float:
    primary = view_raw.split("/")[0].strip()
    key = primary.replace(" ", "_")
    return _VIEW_PREMIUM.get(key, 0.0)


def generate_rows() -> list[dict[str, str]]:
    """Generate the deterministic synthetic catalog rows (CSV dict rows)."""
    rng = random.Random(RNG_SEED)
    rows: list[dict[str, str]] = []

    for complex_name in DEMO_COMPLEX_CITIES:
        city = DEMO_COMPLEX_CITIES[complex_name]
        mix = _ROOM_MIX.copy()
        rng.shuffle(mix)

        for idx, rooms in enumerate(mix, start=1):
            band = _PRICE_RANGE_OVERRIDES.get((city, rooms), _PRICE_RANGE[rooms])
            base = rng.randrange(band[0], band[1] + 1, 500)
            view_raw = rng.choice(_VIEWS)
            price = _clamp_band(
                _round_to_step(base * (1.0 + _view_premium(view_raw)), 500), band
            )

            lo, hi = _AREA_RANGE[rooms]
            area = round(rng.uniform(lo, hi), 1)

            floor_num = rng.choice([0, 1, 1, 2, 2, 3, 3, 4, 5, 6, 7])
            floor_label = "gr." if floor_num == 0 else str(floor_num)

            is_furnished = rng.random() < 0.6
            has_floor_plan = rng.random() < 0.3
            has_photo = rng.random() < 0.85
            is_promotion = rng.random() < 0.12
            old_price = _round_to_step(price * 1.08, 1000) if is_promotion else ""

            rows.append(
                {
                    "complex_name": complex_name,
                    "city": city,
                    "section": _SECTIONS[(idx - 1) % len(_SECTIONS)],
                    "apartment_number": str(100 + idx),
                    "rooms": str(rooms),
                    "floor_label": floor_label,
                    "area_m2": f"{area}",
                    "view_raw": view_raw,
                    "price_eur": str(price),
                    "price_bgn": f"{round(price * BGN_PER_EUR, 2)}",
                    "is_furnished": str(is_furnished).lower(),
                    "has_floor_plan": str(has_floor_plan).lower(),
                    "has_photo": str(has_photo).lower(),
                    "is_promotion": str(is_promotion).lower(),
                    "old_price_eur": str(old_price),
                }
            )

    return rows


def rows_to_csv(rows: list[dict[str, str]]) -> str:
    """Serialize rows to CSV text (deterministic, trailing newline)."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _load_rows(csv_path: Path) -> list[dict[str, str]]:
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != CSV_COLUMNS:
            raise SystemExit(
                f"Unexpected CSV columns in {csv_path}: {reader.fieldnames}"
            )
        return list(reader)


def validate_rows(rows: list[dict[str, str]]) -> None:
    """Check the structural truthfulness invariants of the catalog.

    Combinatorial guarantees only — the production-path (extractor → filter)
    verification lives in tests/unit/services/test_demo_seed_truthfulness.py.
    """
    if not rows:
        raise SystemExit("Seed is empty")

    cities = {r["city"] for r in rows}
    complexes = {r["complex_name"] for r in rows}
    unknown_cities = cities - set(DEMO_CITIES)
    unknown_complexes = complexes - set(DEMO_COMPLEX_CITIES)
    if unknown_cities or unknown_complexes:
        raise SystemExit(f"Seed drifts from demo domain: {unknown_cities}, {unknown_complexes}")

    identities = [(r["complex_name"], r["section"], r["apartment_number"]) for r in rows]
    if len(identities) != len(set(identities)):
        raise SystemExit("Duplicate (complex, section, apartment_number) rows")

    def count_cheap(city: str, rooms: int, max_price: int) -> int:
        return sum(
            1
            for r in rows
            if r["city"] == city and int(r["rooms"]) == rooms and float(r["price_eur"]) <= max_price
        )

    def count_expensive(city: str, min_price: int) -> int:
        return sum(
            1 for r in rows if r["city"] == city and float(r["price_eur"]) >= min_price
        )

    pfb_rooms3 = sum(
        1 for r in rows if r["complex_name"] == "Premier Fort Beach" and int(r["rooms"]) == 3
    )
    guarantees = [
        ("Солнечный берег rooms=1 ≤ 100k", count_cheap("Солнечный берег", 1, 100_000)),
        ("Premier Fort Beach rooms=3", pfb_rooms3),
        ("Элените rooms=4 ≤ 200k", count_cheap("Элените", 4, 200_000)),
        ("Свети Влас ≥ 150k", count_expensive("Свети Влас", 150_000)),
    ]

    failures = [f"{name}: {n} (< 3)" for name, n in guarantees if n < 3]
    if failures:
        raise SystemExit("Golden-query guarantees broken: " + "; ".join(failures))

    no_result = count_cheap("Свети Влас", 4, 60_000)
    if no_result != 0:
        raise SystemExit(f"No-result guarantee broken: Свети Влас rooms=4 ≤ 60k has {no_result} rows")

    view_primaries = {r["view_raw"].split("/")[0].strip().replace(" ", "_") for r in rows}
    missing_views = {"sea", "pool", "garden", "forest"} - view_primaries
    if missing_views:
        raise SystemExit(f"Seed misses view options: {missing_views}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the existing seed is byte-identical to the generator output",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=DEFAULT_CSV_PATH,
        help="seed path (default: data/apartments.csv)",
    )
    args = parser.parse_args()

    rows = generate_rows()
    validate_rows(rows)

    if args.check:
        expected = rows_to_csv(rows)
        actual = args.csv.read_text(encoding="utf-8")
        if actual != expected:
            raise SystemExit(
                f"{args.csv} is out of date. Run: "
                f"uv run python scripts/apartments/generate_seed.py"
            )
        print(f"OK: {args.csv} matches the deterministic generator ({len(rows)} rows).")
        return

    args.csv.write_text(rows_to_csv(rows), encoding="utf-8")
    print(f"Wrote {len(rows)} synthetic apartments to {args.csv}.")


if __name__ == "__main__":
    main()
