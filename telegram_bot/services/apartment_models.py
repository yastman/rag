# telegram_bot/services/apartment_models.py
"""Data models for apartment catalog in Qdrant."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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

    Handles: "ultra sea panorama", "sea/garden", "pool/sea", etc.
    Returns: ("sea", ["sea", "garden"]) for "sea/garden"
    """
    raw = raw.strip().lower()
    if not raw:
        return ("", [])

    # Slash-separated FIRST: expand tags from all parts, use synonym for primary
    if "/" in raw:
        parts = [p.strip() for p in raw.split("/")]
        all_tags: list[str] = []
        for p in parts:
            normalized = _VIEW_SYNONYMS.get(p, p.replace(" ", "_"))
            all_tags.extend(_VIEW_TAG_MAP.get(normalized, [normalized]))
        # Use synonym for primary if the combined string is recognized
        if raw in _VIEW_SYNONYMS:
            primary_normalized = _VIEW_SYNONYMS[raw]
        else:
            primary_normalized = _VIEW_SYNONYMS.get(parts[0], parts[0].replace(" ", "_"))
        return (primary_normalized, list(dict.fromkeys(all_tags)))

    # Check exact synonym (non-slash inputs only)
    if raw in _VIEW_SYNONYMS:
        primary = _VIEW_SYNONYMS[raw]
        tags = list(_VIEW_TAG_MAP.get(primary, [primary]))
        return (primary, tags)

    # Single word or phrase
    normalized = raw.replace(" ", "_")
    tags = list(_VIEW_TAG_MAP.get(normalized, [normalized]))
    return (normalized, tags)


def _parse_bool(raw: object) -> bool:
    """Parse bool-like values from CSV/JSON sources."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    if isinstance(raw, str):
        normalized = raw.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(raw)


# --- Records ---


@dataclass(frozen=True, slots=True)
class ApartmentRecord:
    """Single apartment listing for Qdrant ingestion."""

    complex_name: str
    city: str
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
    is_promotion: bool = False
    old_price_eur: float | None = None

    @classmethod
    def from_raw(cls, row: dict) -> ApartmentRecord:
        """Create from raw data dict (CSV row or parsed HTML)."""
        floor_label = str(row.get("floor_label", "0"))
        floor = 0 if floor_label.lower().startswith("gr") else int(floor_label)

        view_primary, view_tags = normalize_view(str(row.get("view_raw", "")))

        return cls(
            complex_name=str(row["complex_name"]),
            city=str(row.get("city", "")),
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
            is_furnished=_parse_bool(row.get("is_furnished", False)),
            has_floor_plan=_parse_bool(row.get("has_floor_plan", False)),
            has_photo=_parse_bool(row.get("has_photo", False)),
            is_promotion=_parse_bool(row.get("is_promotion", False)),
            old_price_eur=float(row["old_price_eur"]) if row.get("old_price_eur") else None,
        )

    def to_description(self) -> str:
        """Generate natural language description for embedding."""
        furnished = "С мебелью" if self.is_furnished else "Без мебели"
        floor_str = "цокольный этаж" if self.floor == 0 else f"{self.floor} этаж"
        price_fmt = f"{self.price_eur:,.0f}".replace(",", " ")
        view_str = ", ".join(self.view_tags) if self.view_tags else "не указан"
        city_str = f"{self.city}, " if self.city else ""
        rooms_word = {
            1: "Студио",
            2: "2 комнаты (1 спальня)",
            3: "3 комнаты (2 спальни)",
            4: "4 комнаты (3 спальни)",
        }.get(self.rooms, f"{self.rooms} комнат")

        return (
            f"{city_str}{self.complex_name}, секция {self.section}, "
            f"апартамент {self.apartment_number}. "
            f"{rooms_word}, {floor_str}, {self.area_m2} м². "
            f"Вид: {view_str}. Цена: {price_fmt} €. {furnished}."
        )

    def to_payload(self) -> dict:
        """Build Qdrant point payload (top-level fields, no metadata. prefix)."""
        return {
            "complex_name": self.complex_name,
            "city": self.city,
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
            "is_promotion": self.is_promotion,
            "old_price_eur": self.old_price_eur,
            "description": self.to_description(),
        }

    def to_hybrid_description(self) -> str:
        """Hybrid text for BGE-M3: structured prefix + NL body.

        Prefix helps sparse/lexical retrieval (exact numbers).
        Body helps dense/semantic retrieval (conceptual queries).
        """
        price_k = int(self.price_eur / 1000)
        prefix = f"[{self.rooms}BR|{self.area_m2}m2|{price_k}kEUR]"
        body = self.to_description()
        promo = " Акция!" if self.is_promotion else ""
        return f"{prefix} {body}{promo}"


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
    city: str | None = None
    complex_name: str | None = None
    view_tags: list[str] = field(default_factory=list)
    section: str | None = None

    # Meta
    semantic_query: str = ""
    confidence: str = "LOW"
    score: int = 0
    conflicts: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
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
    """Score and assign confidence level. Returns new instance.

    3-level confidence gate with critical slot tracking:
    - HIGH: has critical slot (city OR complex_name) AND at least one hard numeric filter
    - MEDIUM: has critical slot OR hard filter, but not both
    - LOW: no filters extracted
    """
    if parse_result.conflicts:
        return replace(
            parse_result, confidence="LOW", score=-1, missing_fields=["city", "complex_name"]
        )

    score = 0
    has_hard = False
    has_critical = False

    # Hard numeric filters
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

    # Critical slots: city OR complex_name
    if getattr(parse_result, "city", None) is not None:
        score += 2
        has_critical = True
    if parse_result.complex_name is not None:
        score += 2
        has_critical = True

    # Secondary entity filters
    if parse_result.view_tags:
        score += 1
    if parse_result.section is not None:
        score += 1

    # Track missing critical slots for LLM to fill
    missing_fields: list[str] = [] if has_critical else ["city", "complex_name"]

    # Confidence mapping
    if has_critical and has_hard:
        confidence = "HIGH"
    elif has_critical or has_hard:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return replace(parse_result, confidence=confidence, score=score, missing_fields=missing_fields)


# --- Pydantic extraction models (hybrid pipeline) ---


class HardFilters(BaseModel):
    """Hard filters that map directly to Qdrant payload conditions."""

    city: str | None = None
    rooms: int | None = None
    min_price_eur: float | None = None
    max_price_eur: float | None = None
    min_area_m2: float | None = None
    max_area_m2: float | None = None
    min_floor: int | None = None
    max_floor: int | None = None
    complex_name: str | None = None
    view_tags: list[str] = Field(default_factory=list)
    section: str | None = None
    is_furnished: bool | None = None

    @model_validator(mode="after")
    def fix_ranges(self) -> HardFilters:
        """Auto-swap inverted ranges so min <= max."""
        if (
            self.min_price_eur is not None
            and self.max_price_eur is not None
            and self.min_price_eur > self.max_price_eur
        ):
            self.min_price_eur, self.max_price_eur = self.max_price_eur, self.min_price_eur
        if (
            self.min_area_m2 is not None
            and self.max_area_m2 is not None
            and self.min_area_m2 > self.max_area_m2
        ):
            self.min_area_m2, self.max_area_m2 = self.max_area_m2, self.min_area_m2
        if (
            self.min_floor is not None
            and self.max_floor is not None
            and self.min_floor > self.max_floor
        ):
            self.min_floor, self.max_floor = self.max_floor, self.min_floor
        return self

    def to_filters_dict(self) -> dict | None:
        """Convert to Qdrant-compatible filters dict for _build_apartment_filter()."""
        f: dict = {}
        if self.city is not None:
            f["city"] = self.city
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
            f["view_tags"] = self.view_tags
        if self.is_furnished is not None:
            f["is_furnished"] = self.is_furnished
        return f or None


class SoftPreferences(BaseModel):
    """Мягкие предпочтения — boosting в semantic search, не отсекают результаты."""

    near_sea: bool = Field(False, description="Близко к морю")
    spacious: bool = Field(False, description="Просторная")
    budget_friendly: bool = Field(False, description="Недорого/бюджетно")
    high_floor: bool = Field(False, description="Высокий этаж")
    quiet: bool = Field(False, description="Тихое место")
    sort_bias: Literal["price_asc", "price_desc", "area_desc", "floor_desc", "relevance"] = (
        "relevance"
    )

    def to_semantic_parts(self) -> list[str]:
        """Convert preferences to semantic query fragments."""
        parts: list[str] = []
        if self.near_sea:
            parts.append("близко к морю")
        if self.spacious:
            parts.append("просторная квартира")
        if self.budget_friendly:
            parts.append("недорого бюджетно")
        if self.high_floor:
            parts.append("высокий этаж")
        if self.quiet:
            parts.append("тихое спокойное место")
        return parts


class ExtractionMeta(BaseModel):
    """Метаданные извлечения для мониторинга и отладки."""

    source: Literal["regex", "llm", "hybrid"] = "regex"
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    score: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    normalized_query: str = ""
    semantic_remainder: str = ""


class ApartmentSearchFilters(BaseModel):
    """Полный результат extraction pipeline."""

    hard: HardFilters = Field(default_factory=lambda: HardFilters())
    soft: SoftPreferences = Field(default_factory=lambda: SoftPreferences())  # type: ignore[call-arg]
    meta: ExtractionMeta = Field(default_factory=lambda: ExtractionMeta())

    def build_semantic_query(self) -> str:
        """Build semantic query from preferences + remainder text."""
        parts: list[str] = []
        if self.meta.semantic_remainder:
            parts.append(self.meta.semantic_remainder)
        parts.extend(self.soft.to_semantic_parts())
        return " ".join(parts) if parts else "апартамент"
