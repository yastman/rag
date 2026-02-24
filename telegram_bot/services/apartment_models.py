"""Data models for apartment catalog in Qdrant."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


# --- View normalization ---

_VIEW_SYNONYMS: dict[str, str] = {
    "ultra sea panorama": "ultra_sea_panorama",
    "ultra sea view": "ultra_sea_panorama",
    "ultra sea": "ultra_sea",
    "sea panorama": "sea_panorama",
    "sea panorama/forest": "sea_panorama",
    "garden/forest": "garden",
    "garden/pool": "garden",
    "pool/garden": "pool",
    "pool/sea": "pool",
    "backyard": "garden",
}

_VIEW_TAG_MAP: dict[str, list[str]] = {
    "ultra_sea_panorama": ["sea", "panorama"],
    "ultra_sea": ["sea"],
    "sea_panorama": ["sea", "panorama"],
    "sea": ["sea"],
    "pool": ["pool"],
    "garden": ["garden"],
    "forest": ["forest"],
}


def normalize_view(raw: str) -> tuple[str, list[str]]:
    """Normalize view string to (primary, tags).

    Handles: "ultra sea panorama", "sea/garden", "garden/pool", etc.
    Returns: ("sea", ["sea", "garden"]) for "sea/garden"
    """
    raw = raw.strip().lower()
    if not raw:
        return ("", [])

    # Check exact synonym first
    if raw in _VIEW_SYNONYMS:
        primary = _VIEW_SYNONYMS[raw]
        tags = list(_VIEW_TAG_MAP.get(primary, [primary]))
        return (primary, tags)

    # Handle slash-separated: "sea/garden" → primary="sea", tags=["sea","garden"]
    if "/" in raw:
        parts = [p.strip() for p in raw.split("/")]
        all_tags: list[str] = []
        for p in parts:
            normalized = _VIEW_SYNONYMS.get(p, p.replace(" ", "_"))
            all_tags.extend(_VIEW_TAG_MAP.get(normalized, [normalized]))
        primary_normalized = _VIEW_SYNONYMS.get(parts[0], parts[0].replace(" ", "_"))
        return (primary_normalized, list(dict.fromkeys(all_tags)))

    # Single word or phrase
    normalized = raw.replace(" ", "_")
    tags = list(_VIEW_TAG_MAP.get(normalized, [normalized]))
    return (normalized, tags)


# --- Records ---


@dataclass(frozen=True, slots=True)
class ApartmentRecord:
    """Single apartment listing for Qdrant ingestion."""

    complex_name: str
    section: str
    apartment_number: str
    rooms: int
    floor: int
    floor_label: str
    area_m2: float
    view_primary: str
    view_tags: list[str]
    price_eur: float
    price_bgn: float
    is_furnished: bool
    has_floor_plan: bool
    has_photo: bool

    @classmethod
    def from_raw(cls, row: dict) -> ApartmentRecord:
        """Create from raw data dict (CSV row or parsed HTML)."""
        floor_label = str(row.get("floor_label", "0"))
        floor = 0 if floor_label.lower().startswith("gr") else int(floor_label)

        view_primary, view_tags = normalize_view(str(row.get("view_raw", "")))

        return cls(
            complex_name=str(row["complex_name"]),
            section=str(row["section"]),
            apartment_number=str(row["apartment_number"]),
            rooms=int(row["rooms"]),
            floor=floor,
            floor_label=floor_label,
            area_m2=float(row["area_m2"]),
            view_primary=view_primary,
            view_tags=view_tags,
            price_eur=float(row["price_eur"]),
            price_bgn=float(row.get("price_bgn", 0)),
            is_furnished=bool(row.get("is_furnished", False)),
            has_floor_plan=bool(row.get("has_floor_plan", False)),
            has_photo=bool(row.get("has_photo", False)),
        )

    def to_description(self) -> str:
        """Generate natural language description for embedding."""
        furnished = "С мебелью" if self.is_furnished else "Без мебели"
        floor_str = "цокольный этаж" if self.floor == 0 else f"{self.floor} этаж"
        price_fmt = f"{self.price_eur:,.0f}".replace(",", " ")
        view_str = ", ".join(self.view_tags) if self.view_tags else "не указан"
        rooms_word = {
            1: "Студио",
            2: "2 комнаты (1 спальня)",
            3: "3 комнаты (2 спальни)",
            4: "4 комнаты (3 спальни)",
        }.get(self.rooms, f"{self.rooms} комнат")

        return (
            f"{self.complex_name}, секция {self.section}, "
            f"апартамент {self.apartment_number}. "
            f"{rooms_word}, {floor_str}, {self.area_m2} м². "
            f"Вид: {view_str}. Цена: {price_fmt} €. {furnished}."
        )

    def to_payload(self) -> dict:
        """Build Qdrant point payload (top-level fields, no metadata. prefix)."""
        return {
            "complex_name": self.complex_name,
            "section": self.section,
            "apartment_number": self.apartment_number,
            "rooms": self.rooms,
            "floor": self.floor,
            "floor_label": self.floor_label,
            "area_m2": self.area_m2,
            "view_primary": self.view_primary,
            "view_tags": self.view_tags,
            "price_eur": self.price_eur,
            "price_bgn": self.price_bgn,
            "is_furnished": self.is_furnished,
            "has_floor_plan": self.has_floor_plan,
            "has_photo": self.has_photo,
            "description": self.to_description(),
        }


# --- Query parse result ---


@dataclass
class ApartmentQueryParseResult:
    """Parsed apartment search query with confidence scoring."""

    # Hard filters (numeric)
    rooms: int | None = None
    min_price_eur: float | None = None
    max_price_eur: float | None = None
    min_area_m2: float | None = None
    max_area_m2: float | None = None
    min_floor: int | None = None
    max_floor: int | None = None
    is_furnished: bool | None = None

    # Entity filters
    complex_name: str | None = None
    view_tags: list[str] = field(default_factory=list)
    section: str | None = None

    # Meta
    semantic_query: str = ""
    confidence: str = "LOW"
    score: int = 0
    conflicts: list[str] = field(default_factory=list)
    raw_query: str = ""

    def to_filters_dict(self) -> dict:
        """Convert to Qdrant-compatible filters dict for _build_apartment_filter()."""
        f: dict = {}
        if self.rooms is not None:
            f["rooms"] = self.rooms
        if self.min_price_eur is not None or self.max_price_eur is not None:
            price_range: dict = {}
            if self.min_price_eur is not None:
                price_range["gte"] = self.min_price_eur
            if self.max_price_eur is not None:
                price_range["lte"] = self.max_price_eur
            f["price_eur"] = price_range
        if self.min_area_m2 is not None or self.max_area_m2 is not None:
            area_range: dict = {}
            if self.min_area_m2 is not None:
                area_range["gte"] = self.min_area_m2
            if self.max_area_m2 is not None:
                area_range["lte"] = self.max_area_m2
            f["area_m2"] = area_range
        if self.min_floor is not None or self.max_floor is not None:
            floor_range: dict = {}
            if self.min_floor is not None:
                floor_range["gte"] = self.min_floor
            if self.max_floor is not None:
                floor_range["lte"] = self.max_floor
            f["floor"] = floor_range
        if self.complex_name is not None:
            f["complex_name"] = self.complex_name
        if self.view_tags:
            f["view_tags"] = self.view_tags  # handled by MatchAny
        if self.section is not None:
            f["section"] = self.section
        if self.is_furnished is not None:
            f["is_furnished"] = self.is_furnished
        return f


def compute_confidence(parse_result: ApartmentQueryParseResult) -> ApartmentQueryParseResult:
    """Score and assign confidence level. Returns new instance."""
    if parse_result.conflicts:
        return replace(parse_result, confidence="LOW", score=-1)

    score = 0
    has_hard = False
    has_entity = False

    # Hard filters
    if parse_result.rooms is not None:
        score += 2
        has_hard = True
    if parse_result.min_price_eur is not None or parse_result.max_price_eur is not None:
        score += 2
        has_hard = True
    if parse_result.min_area_m2 is not None or parse_result.max_area_m2 is not None:
        score += 1
        has_hard = True
    if parse_result.min_floor is not None or parse_result.max_floor is not None:
        score += 1
        has_hard = True

    # Entity filters
    if parse_result.complex_name is not None:
        score += 2
        has_entity = True
    if parse_result.view_tags:
        score += 1
        has_entity = True
    if parse_result.section is not None:
        score += 1
        has_entity = True

    # Confidence mapping
    if score >= 4 and has_hard and has_entity:
        confidence = "HIGH"
    elif score >= 2:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return replace(parse_result, confidence=confidence, score=score)
