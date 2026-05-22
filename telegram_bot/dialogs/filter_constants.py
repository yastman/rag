"""Shared filter constants and helpers for funnel dialog and filter dialog.

Single source of truth for all apartment filter maps and coercion logic.
"""

from __future__ import annotations

from typing import Any

from telegram_bot.constants.apartment_constants import APARTMENT_CITY_OPTIONS


# ============================================================
# City options — (label, value) pairs for dialog Select
# ============================================================

CITY_OPTIONS: list[tuple[str, str]] = APARTMENT_CITY_OPTIONS

# ============================================================
# Rooms options — (label, int_value) pairs
# ============================================================

ROOMS_OPTIONS: list[tuple[str, int]] = [
    ("Студия", 1),
    ("1-спальня", 2),
    ("2-спальни", 3),
    ("3-спальни", 4),
    ("4+ спальни", 5),
]

ROOMS_DISPLAY: dict[int, str] = {
    0: "Студия",
    1: "Студия",
    2: "1-спальня",
    3: "2-спальни",
    4: "3-спальни",
    5: "4+ спальни",
}

# Property type → rooms (used by funnel)
ROOMS_MAP: dict[str, int | list[int]] = {"studio": [0, 1], "1bed": 2, "2bed": 3, "3bed": 4}

# ============================================================
# Budget
# ============================================================

BUDGET_MAP: dict[str, dict[str, int]] = {
    "low": {"lte": 50_000},
    "mid": {"gte": 50_000, "lte": 100_000},
    "high": {"gte": 100_000, "lte": 150_000},
    "premium": {"gte": 150_000, "lte": 200_000},
    "luxury": {"gte": 200_000},
}

BUDGET_DISPLAY: dict[str, str] = {
    "low": "До 50 000 €",
    "mid": "50 000 – 100 000 €",
    "high": "100 000 – 150 000 €",
    "premium": "150 000 – 200 000 €",
    "luxury": "Более 200 000 €",
}

BUDGET_OPTIONS: list[tuple[str, str]] = [
    (BUDGET_DISPLAY[key], key) for key in ("low", "mid", "high", "premium", "luxury")
]

# ============================================================
# Floor
# ============================================================

FLOOR_MAP: dict[str, dict[str, int]] = {
    "low": {"gte": 0, "lte": 1},
    "mid": {"gte": 2, "lte": 3},
    "high": {"gte": 4, "lte": 5},
    "top": {"gte": 6},
}

FLOOR_DISPLAY: dict[str, str] = {
    "low": "0-1 этаж",
    "mid": "2-3 этаж",
    "high": "4-5 этаж",
    "top": "6+ этаж",
}

FLOOR_OPTIONS: list[tuple[str, str]] = [
    (FLOOR_DISPLAY[key], key) for key in ("low", "mid", "high", "top")
]

# ============================================================
# Area
# ============================================================

AREA_MAP: dict[str, dict[str, int]] = {
    "small": {"lte": 40},
    "mid": {"gte": 40, "lte": 60},
    "large": {"gte": 60, "lte": 80},
    "xlarge": {"gte": 80, "lte": 120},
    "xxlarge": {"gte": 120},
}

AREA_DISPLAY: dict[str, str] = {
    "small": "До 40 m²",
    "mid": "40–60 m²",
    "large": "60–80 m²",
    "xlarge": "80–120 m²",
    "xxlarge": "120+ m²",
}

AREA_OPTIONS: list[tuple[str, str]] = [
    (AREA_DISPLAY[key], key) for key in ("small", "mid", "large", "xlarge", "xxlarge")
]

# ============================================================
# View
# ============================================================

VIEW_DISPLAY: dict[str, str] = {
    "sea": "Море",
    "sea_panorama": "Панорама моря",
    "ultra_sea_panorama": "Ультра панорама моря",
    "ultra_sea": "Ультра море",
    "pool": "Бассейн",
    "garden": "Газон/сад",
    "forest": "Лес/горы",
}

VIEW_OPTIONS: list[tuple[str, str]] = [(display, key) for key, display in VIEW_DISPLAY.items()]

# ============================================================
# Field → filter key mapping
# ============================================================

FIELD_TO_FILTER_KEY: dict[str, str] = {
    "city": "city",
    "rooms": "rooms",
    "budget": "price_eur",
    "view": "view_tags",
    "area": "area_m2",
    "floor": "floor",
    "complex": "complex_name",
    "furnished": "is_furnished",
    "promotion": "is_promotion",
}

# ============================================================
# Coercion helper
# ============================================================


def coerce_filter_value(field: str, value: str) -> Any:
    """Coerce a string item_id from Radio widget to the correct Qdrant filter type."""
    if not value:
        return None
    if field == "rooms":
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    if field == "floor":
        if value in FLOOR_MAP:
            return FLOOR_MAP[value]
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    if field == "area":
        if value in AREA_MAP:
            return AREA_MAP[value]
        try:
            return {"gte": int(value)}
        except (ValueError, TypeError):
            return None
    if field == "budget":
        return BUDGET_MAP.get(value)
    if field in ("furnished", "promotion"):
        if value == "true":
            return True
        if value == "false":
            return False
        return None
    if field == "view":
        return [value] if value else None
    return value or None


# ============================================================
# Build filters dict from raw dialog / FSMContext data
# ============================================================


def build_filters_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert raw filter data to apartment_filters dict.

    Handles:
    - String item_ids from Radio widgets → coerce via coerce_filter_value
    - Already-typed values (int, dict, bool) → passthrough
    - Field name translation via FIELD_TO_FILTER_KEY (complex → complex_name, etc.)
    - budget → price_eur coercion
    - None / "" / "any" → excluded
    """
    result: dict[str, Any] = {}
    for field, value in raw.items():
        if value is None or value == "" or value == "any" or value == "None":
            continue
        # Coerce string item_ids from Radio widgets; passthrough typed values
        coerced = coerce_filter_value(field, value) if isinstance(value, str) else value
        if coerced is None:
            continue
        if field == "budget":
            if isinstance(coerced, dict):
                result["price_eur"] = coerced
        else:
            filter_key = FIELD_TO_FILTER_KEY.get(field, field)
            result[filter_key] = coerced
    return result
