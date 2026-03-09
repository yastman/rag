# Apartment Text Search: Hybrid Extraction Pipeline — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Заменить regex-only парсер на hybrid pipeline (normalizer → regex → confidence gate → Instructor LLM fallback) с разделением hard_filters / soft_preferences.

**Architecture:** 3-tier extraction: (1) нормализация алиасов, (2) улучшенный regex с городами, (3) Instructor + gpt-4o-mini для unresolved slots. Единая Pydantic-модель `ApartmentSearchFilters` с `HardFilters`, `SoftPreferences`, `ExtractionMeta`. Redis-кэш LLM-экстракций.

**Tech Stack:** Python 3.12, Pydantic v2, Instructor >=1.7, OpenAI SDK (через LiteLLM), Qdrant, Redis, Langfuse

**Design doc:** `docs/plans/2026-03-06-apartment-text-search-design.md`

---

## Task 1: Pydantic-модели (HardFilters, SoftPreferences, ExtractionMeta, ApartmentSearchFilters)

**Files:**
- Create: `tests/unit/services/test_apartment_search_filters.py`
- Modify: `telegram_bot/services/apartment_models.py`

**Step 1: Write failing tests**

```python
# tests/unit/services/test_apartment_search_filters.py
"""Tests for ApartmentSearchFilters Pydantic models."""

import pytest

from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)


class TestHardFilters:
    def test_defaults_all_none(self):
        f = HardFilters()
        assert f.city is None
        assert f.rooms is None
        assert f.min_price_eur is None

    def test_price_range_auto_swap(self):
        f = HardFilters(min_price_eur=200000, max_price_eur=100000)
        assert f.min_price_eur == 100000
        assert f.max_price_eur == 200000

    def test_area_range_auto_swap(self):
        f = HardFilters(min_area_m2=120, max_area_m2=60)
        assert f.min_area_m2 == 60
        assert f.max_area_m2 == 120

    def test_floor_range_auto_swap(self):
        f = HardFilters(min_floor=5, max_floor=2)
        assert f.min_floor == 2
        assert f.max_floor == 5

    def test_no_swap_when_valid(self):
        f = HardFilters(min_price_eur=100000, max_price_eur=200000)
        assert f.min_price_eur == 100000
        assert f.max_price_eur == 200000

    def test_to_filters_dict_full(self):
        f = HardFilters(
            city="Солнечный берег",
            rooms=2,
            min_price_eur=50000,
            max_price_eur=100000,
            view_tags=["sea"],
        )
        d = f.to_filters_dict()
        assert d["city"] == "Солнечный берег"
        assert d["rooms"] == 2
        assert d["price_eur"] == {"gte": 50000, "lte": 100000}
        assert d["view_tags"] == ["sea"]

    def test_to_filters_dict_empty(self):
        f = HardFilters()
        assert f.to_filters_dict() is None

    def test_to_filters_dict_partial_price(self):
        f = HardFilters(max_price_eur=100000)
        d = f.to_filters_dict()
        assert d["price_eur"] == {"lte": 100000}


class TestSoftPreferences:
    def test_defaults_all_false(self):
        s = SoftPreferences()
        assert s.near_sea is False
        assert s.spacious is False
        assert s.sort_bias == "relevance"

    def test_to_semantic_parts(self):
        s = SoftPreferences(near_sea=True, spacious=True)
        parts = s.to_semantic_parts()
        assert "близко к морю" in parts
        assert "просторная квартира" in parts

    def test_empty_semantic_parts(self):
        s = SoftPreferences()
        assert s.to_semantic_parts() == []


class TestExtractionMeta:
    def test_defaults(self):
        m = ExtractionMeta()
        assert m.source == "regex"
        assert m.confidence == "LOW"


class TestApartmentSearchFilters:
    def test_defaults(self):
        f = ApartmentSearchFilters()
        assert f.hard.city is None
        assert f.soft.near_sea is False
        assert f.meta.source == "regex"

    def test_build_semantic_query_with_remainder(self):
        f = ApartmentSearchFilters(
            soft=SoftPreferences(near_sea=True),
            meta=ExtractionMeta(semantic_remainder="уютная"),
        )
        q = f.build_semantic_query()
        assert "уютная" in q
        assert "близко к морю" in q

    def test_build_semantic_query_empty(self):
        f = ApartmentSearchFilters()
        assert f.build_semantic_query() == "апартамент"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_apartment_search_filters.py -v`
Expected: FAIL — `ImportError: cannot import name 'HardFilters'`

**Step 3: Implement models**

Add to `telegram_bot/services/apartment_models.py` (after existing code, line ~305):

```python
# --- New Pydantic models for hybrid extraction pipeline ---


class HardFilters(BaseModel):
    """Жесткие фильтры — строят Qdrant Filter(must=[...])."""

    city: str | None = Field(None, description="Город: Солнечный берег, Свети Влас, Элените")
    complex_name: str | None = Field(None, description="Название комплекса")
    rooms: int | None = Field(None, ge=1, le=5, description="Количество комнат (1=студия)")
    min_price_eur: float | None = Field(None, ge=0, description="Мин. цена EUR")
    max_price_eur: float | None = Field(None, ge=0, description="Макс. цена EUR")
    min_area_m2: float | None = Field(None, ge=0, description="Мин. площадь м2")
    max_area_m2: float | None = Field(None, ge=0, description="Макс. площадь м2")
    min_floor: int | None = Field(None, ge=0, description="Мин. этаж (0=цоколь)")
    max_floor: int | None = Field(None, description="Макс. этаж")
    view_tags: list[str] | None = Field(None, description="Вид: sea, pool, garden, forest, panorama")
    is_furnished: bool | None = Field(None, description="С мебелью")

    @model_validator(mode="after")
    def fix_ranges(self) -> HardFilters:
        if self.min_price_eur and self.max_price_eur and self.min_price_eur > self.max_price_eur:
            self.min_price_eur, self.max_price_eur = self.max_price_eur, self.min_price_eur
        if self.min_area_m2 and self.max_area_m2 and self.min_area_m2 > self.max_area_m2:
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
        if self.complex_name is not None:
            f["complex_name"] = self.complex_name
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

    hard: HardFilters = Field(default_factory=HardFilters)
    soft: SoftPreferences = Field(default_factory=SoftPreferences)
    meta: ExtractionMeta = Field(default_factory=ExtractionMeta)

    def build_semantic_query(self) -> str:
        """Build semantic query from preferences + remainder text."""
        parts: list[str] = []
        if self.meta.semantic_remainder:
            parts.append(self.meta.semantic_remainder)
        parts.extend(self.soft.to_semantic_parts())
        return " ".join(parts) if parts else "апартамент"
```

Note: нужен import `Literal` из typing и `BaseModel, Field, model_validator` из pydantic (уже есть `dataclass, field, replace` — добавить pydantic imports).

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/services/test_apartment_search_filters.py -v`
Expected: All PASS

**Step 5: Run full check**

Run: `make check`
Expected: PASS (ruff + mypy)

**Step 6: Commit**

```bash
git add telegram_bot/services/apartment_models.py tests/unit/services/test_apartment_search_filters.py
git commit -m "feat(apartments): add HardFilters, SoftPreferences, ApartmentSearchFilters Pydantic models"
```

---

## Task 2: Словарь городов + city extraction в regex парсере

**Files:**
- Modify: `tests/unit/services/test_apartment_filter_extractor.py`
- Modify: `telegram_bot/services/apartment_filter_extractor.py`

**Step 1: Write failing tests**

Add to `tests/unit/services/test_apartment_filter_extractor.py`:

```python
class TestCity:
    @pytest.mark.parametrize(
        ("query", "expected_city"),
        [
            ("двушка солнечный берег", "Солнечный берег"),
            ("студия sunny beach", "Солнечный берег"),
            ("квартира в свети влас", "Свети Влас"),
            ("апартамент святой влас", "Свети Влас"),
            ("элените 3 комнаты", "Элените"),
            ("elenite apartment", "Элените"),
            ("санни бич до 100к", "Солнечный берег"),
            ("двушка в несебре", None),  # несебр — не в нашей БД
        ],
    )
    def test_city_extraction(self, query: str, expected_city: str | None) -> None:
        result = _ext.parse(query)
        assert result.city == expected_city


class TestCityAndComplex:
    def test_city_consumed_from_semantic(self) -> None:
        result = _ext.parse("уютная двушка солнечный берег до 100к")
        assert result.city == "Солнечный берег"
        assert "солнечный берег" not in result.semantic_query.lower()

    def test_city_and_complex_together(self) -> None:
        result = _ext.parse("премьер форт свети влас")
        assert result.city == "Свети Влас"
        assert result.complex_name == "Premier Fort Beach"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_apartment_filter_extractor.py::TestCity -v`
Expected: FAIL — `AttributeError: 'ApartmentQueryParseResult' object has no attribute 'city'`

**Step 3: Implement city extraction**

In `telegram_bot/services/apartment_filter_extractor.py`:

1. Add `_CITY_ALIASES` dict and `_CITY_ALIASES_SORTED` (after `_COMPLEX_ALIASES_SORTED`, line ~41):

```python
_CITY_ALIASES: dict[str, str] = {
    "солнечный берег": "Солнечный берег",
    "солнечный": "Солнечный берег",
    "sunny beach": "Солнечный берег",
    "слънчев бряг": "Солнечный берег",
    "санни бич": "Солнечный берег",
    "свети влас": "Свети Влас",
    "святой влас": "Свети Влас",
    "св влас": "Свети Влас",
    "sv vlas": "Свети Влас",
    "sveti vlas": "Свети Влас",
    "saint vlas": "Свети Влас",
    "элените": "Элените",
    "elenite": "Элените",
    "елените": "Элените",
}

_CITY_ALIASES_SORTED = sorted(_CITY_ALIASES, key=len, reverse=True)
```

2. Add `_extract_city()` method to `ApartmentFilterExtractor`:

```python
def _extract_city(self, text: str, consumed: list[tuple[int, int]]) -> str | None:
    for alias in _CITY_ALIASES_SORTED:
        if alias in text:
            start = text.index(alias)
            consumed.append((start, start + len(alias)))
            return _CITY_ALIASES[alias]
    return None
```

3. Add `city` field to `ApartmentQueryParseResult` in `apartment_models.py` (line ~213, after `section`):

```python
city: str | None = None
```

4. Call `_extract_city` in `parse()` method and pass to result, add city to confidence scoring (entity filter, +2 points like complex_name).

5. Update `compute_confidence()` to score city as entity filter:

```python
if parse_result.city is not None:
    score += 2
    has_entity = True
```

6. Update `to_filters_dict()` in `ApartmentQueryParseResult`:

```python
if self.city is not None:
    f["city"] = self.city
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/services/test_apartment_filter_extractor.py -v`
Expected: All PASS (old + new)

**Step 5: Commit**

```bash
git add telegram_bot/services/apartment_filter_extractor.py telegram_bot/services/apartment_models.py tests/unit/services/test_apartment_filter_extractor.py
git commit -m "feat(apartments): add city extraction with alias dictionary"
```

---

## Task 3: Улучшенный confidence gate (3 уровня с critical slots)

**Files:**
- Modify: `tests/unit/services/test_apartment_models.py`
- Modify: `telegram_bot/services/apartment_models.py`

**Step 1: Write failing tests**

Add to `tests/unit/services/test_apartment_models.py`:

```python
class TestComputeConfidenceV2:
    """Updated confidence with critical slots check."""

    def test_high_with_city_and_hard(self):
        r = ApartmentQueryParseResult(rooms=2, max_price_eur=100000, city="Солнечный берег")
        result = compute_confidence(r)
        assert result.confidence == "HIGH"

    def test_medium_rooms_only(self):
        r = ApartmentQueryParseResult(rooms=2)
        result = compute_confidence(r)
        assert result.confidence == "MEDIUM"

    def test_medium_city_only(self):
        r = ApartmentQueryParseResult(city="Свети Влас")
        result = compute_confidence(r)
        assert result.confidence == "MEDIUM"

    def test_low_no_filters(self):
        r = ApartmentQueryParseResult()
        result = compute_confidence(r)
        assert result.confidence == "LOW"

    def test_low_on_conflict(self):
        r = ApartmentQueryParseResult(
            rooms=2, city="Элените", conflicts=["price_conflict:min>max"]
        )
        result = compute_confidence(r)
        assert result.confidence == "LOW"

    def test_missing_fields_tracked(self):
        r = ApartmentQueryParseResult(rooms=2)
        result = compute_confidence(r)
        assert "city" in result.missing_fields or "complex_name" in result.missing_fields
```

**Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/services/test_apartment_models.py::TestComputeConfidenceV2 -v`
Expected: FAIL — `city` attribute or `missing_fields` not found

**Step 3: Update compute_confidence**

In `telegram_bot/services/apartment_models.py`, update `compute_confidence()` (line 262):

```python
def compute_confidence(parse_result: ApartmentQueryParseResult) -> ApartmentQueryParseResult:
    """Score and assign confidence level with critical slot tracking."""
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
    if parse_result.city is not None:
        score += 2
        has_entity = True
    if parse_result.view_tags:
        score += 1
        has_entity = True
    if parse_result.section is not None:
        score += 1
        has_entity = True

    # Track missing critical slots
    missing: list[str] = []
    if parse_result.city is None and parse_result.complex_name is None:
        missing.append("city")
    if parse_result.rooms is None:
        missing.append("rooms")
    if parse_result.min_price_eur is None and parse_result.max_price_eur is None:
        missing.append("price")

    # Confidence mapping
    if score >= 4 and has_hard and has_entity:
        confidence = "HIGH"
    elif score >= 1:
        confidence = "MEDIUM"
    else:
        confidence = "LOW"

    return replace(
        parse_result, confidence=confidence, score=score, missing_fields=missing
    )
```

Add `missing_fields` to `ApartmentQueryParseResult`:

```python
missing_fields: list[str] = field(default_factory=list)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/services/test_apartment_models.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add telegram_bot/services/apartment_models.py tests/unit/services/test_apartment_models.py
git commit -m "feat(apartments): 3-level confidence with critical slot tracking"
```

---

## Task 4: Instructor dependency + LLM extractor service

**Files:**
- Modify: `pyproject.toml`
- Create: `telegram_bot/services/apartment_llm_extractor.py`
- Create: `tests/unit/services/test_apartment_llm_extractor.py`

**Step 1: Add instructor dependency**

```bash
uv add "instructor>=1.7.0"
```

**Step 2: Write failing tests**

```python
# tests/unit/services/test_apartment_llm_extractor.py
"""Tests for Instructor-based LLM apartment filter extraction."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.services.apartment_llm_extractor import (
    ApartmentLlmExtractor,
    EXTRACTION_SYSTEM_PROMPT,
)
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)


@pytest.fixture
def mock_llm_result() -> ApartmentSearchFilters:
    return ApartmentSearchFilters(
        hard=HardFilters(city="Солнечный берег", rooms=2, max_price_eur=100000),
        soft=SoftPreferences(near_sea=True),
        meta=ExtractionMeta(source="llm", confidence="HIGH"),
    )


class TestApartmentLlmExtractor:
    def test_system_prompt_contains_cities(self):
        assert "Солнечный берег" in EXTRACTION_SYSTEM_PROMPT
        assert "Свети Влас" in EXTRACTION_SYSTEM_PROMPT
        assert "Элените" in EXTRACTION_SYSTEM_PROMPT

    def test_system_prompt_contains_complexes(self):
        assert "Premier Fort Beach" in EXTRACTION_SYSTEM_PROMPT
        assert "Messambria Fort Beach" in EXTRACTION_SYSTEM_PROMPT

    @pytest.mark.asyncio
    async def test_extract_full_sets_source_llm(self, mock_llm_result):
        extractor = ApartmentLlmExtractor.__new__(ApartmentLlmExtractor)
        extractor._client = AsyncMock()
        extractor._client.chat.completions.create = AsyncMock(return_value=mock_llm_result)

        result = await extractor.extract(query="просторная у моря")
        assert result.meta.source == "llm"

    @pytest.mark.asyncio
    async def test_extract_partial_sets_source_hybrid(self, mock_llm_result):
        extractor = ApartmentLlmExtractor.__new__(ApartmentLlmExtractor)
        extractor._client = AsyncMock()
        extractor._client.chat.completions.create = AsyncMock(return_value=mock_llm_result)

        partial = HardFilters(rooms=2)
        result = await extractor.extract(query="двушка у моря", partial_filters=partial)
        assert result.meta.source == "hybrid"

    @pytest.mark.asyncio
    async def test_post_validation_rejects_unknown_city(self, mock_llm_result):
        mock_llm_result.hard.city = "Бургас"  # не в нашей БД
        extractor = ApartmentLlmExtractor.__new__(ApartmentLlmExtractor)
        extractor._client = AsyncMock()
        extractor._client.chat.completions.create = AsyncMock(return_value=mock_llm_result)

        result = await extractor.extract(query="квартира в бургасе")
        assert result.hard.city is None  # очищено post-validation

    @pytest.mark.asyncio
    async def test_merge_regex_wins_for_numbers(self):
        from telegram_bot.services.apartment_llm_extractor import merge_extraction_results

        regex = ApartmentSearchFilters(
            hard=HardFilters(rooms=2, max_price_eur=100000),
            meta=ExtractionMeta(source="regex"),
        )
        llm = ApartmentSearchFilters(
            hard=HardFilters(rooms=3, max_price_eur=150000, city="Солнечный берег"),
            soft=SoftPreferences(near_sea=True),
            meta=ExtractionMeta(source="llm"),
        )
        merged = merge_extraction_results(regex, llm)
        assert merged.hard.rooms == 2  # regex wins
        assert merged.hard.max_price_eur == 100000  # regex wins
        assert merged.hard.city == "Солнечный берег"  # LLM fills gap
        assert merged.soft.near_sea is True  # LLM preferences
        assert merged.meta.source == "hybrid"
```

**Step 3: Run to verify fail**

Run: `uv run pytest tests/unit/services/test_apartment_llm_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 4: Implement LLM extractor**

```python
# telegram_bot/services/apartment_llm_extractor.py
"""Instructor-based LLM extractor for apartment search filters."""

from __future__ import annotations

import logging

import instructor
from openai import AsyncOpenAI

from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)

logger = logging.getLogger(__name__)

_VALID_CITIES = {"Солнечный берег", "Свети Влас", "Элените"}

EXTRACTION_SYSTEM_PROMPT = """\
Ты извлекаешь фильтры поиска апартаментов из запроса пользователя.

Контекст: недвижимость в Болгарии (побережье Черного моря).
Города: Солнечный берег, Свети Влас, Элените.
Комплексы: Premier Fort Beach, Prestige Fort Beach, Panorama Fort Beach,
Marina View Fort Beach, Messambria Fort Beach, Imperial Fort Club,
Crown Fort Club, Green Fort Suites, Premier Fort Suites, Nessebar Fort Residence.

Правила:
- Цены всегда в EUR
- "двушка" = 2 комнаты, "студия" = 1 комната
- "у моря" = near_sea preference, НЕ view_tags (если не сказано "вид на море")
- "недорого"/"бюджетно" = budget_friendly preference + sort_bias="price_asc"
- "просторная" = spacious preference + min_area_m2 >= 60
- Если не уверен — оставь None, не выдумывай"""


class ApartmentLlmExtractor:
    """Instructor-based structured extraction from natural language queries."""

    def __init__(self, llm: AsyncOpenAI, model: str = "gpt-4o-mini") -> None:
        self._client = instructor.from_openai(llm)
        self._model = model

    async def extract(
        self,
        query: str,
        partial_filters: HardFilters | None = None,
    ) -> ApartmentSearchFilters:
        """Extract filters using LLM. If partial_filters given, only fill gaps."""
        context = ""
        if partial_filters:
            filled = {k: v for k, v in partial_filters.model_dump().items() if v is not None}
            if filled:
                context = f"\nУже извлечено regex: {filled}\nДоизвлеки остальное."

        result = await self._client.chat.completions.create(
            model=self._model,
            response_model=ApartmentSearchFilters,
            max_retries=2,
            messages=[
                {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": query + context},
            ],
        )

        # Post-validation: reject hallucinated cities
        if result.hard.city and result.hard.city not in _VALID_CITIES:
            logger.warning("LLM hallucinated city=%s, clearing", result.hard.city)
            result.hard.city = None

        result.meta.source = "hybrid" if partial_filters else "llm"
        return result


def merge_extraction_results(
    regex: ApartmentSearchFilters,
    llm: ApartmentSearchFilters,
) -> ApartmentSearchFilters:
    """Merge regex + LLM results. Regex wins for filled fields, LLM fills gaps."""
    merged_hard: dict = {}
    for field_name in HardFilters.model_fields:
        regex_val = getattr(regex.hard, field_name)
        llm_val = getattr(llm.hard, field_name)
        merged_hard[field_name] = regex_val if regex_val is not None else llm_val

    return ApartmentSearchFilters(
        hard=HardFilters(**merged_hard),
        soft=llm.soft,
        meta=ExtractionMeta(
            source="hybrid",
            confidence=llm.meta.confidence,
            normalized_query=regex.meta.normalized_query,
            semantic_remainder=regex.meta.semantic_remainder,
        ),
    )
```

**Step 5: Run tests**

Run: `uv run pytest tests/unit/services/test_apartment_llm_extractor.py -v`
Expected: All PASS

**Step 6: Run full check**

Run: `make check && uv run pytest tests/unit/services/ -v -k apartment`
Expected: All PASS

**Step 7: Commit**

```bash
git add pyproject.toml uv.lock telegram_bot/services/apartment_llm_extractor.py tests/unit/services/test_apartment_llm_extractor.py
git commit -m "feat(apartments): add Instructor-based LLM filter extractor"
```

---

## Task 5: Extraction pipeline orchestrator (confidence gate + cache)

**Files:**
- Create: `telegram_bot/services/apartment_extraction_pipeline.py`
- Create: `tests/unit/services/test_apartment_extraction_pipeline.py`

**Step 1: Write failing tests**

```python
# tests/unit/services/test_apartment_extraction_pipeline.py
"""Tests for the apartment extraction pipeline orchestrator."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from telegram_bot.services.apartment_extraction_pipeline import ApartmentExtractionPipeline
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)


@pytest.fixture
def mock_regex_extractor():
    from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor
    return ApartmentFilterExtractor()


@pytest.fixture
def mock_llm_extractor():
    ext = AsyncMock()
    ext.extract = AsyncMock(
        return_value=ApartmentSearchFilters(
            hard=HardFilters(city="Солнечный берег", rooms=2, max_price_eur=100000),
            soft=SoftPreferences(near_sea=True),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
    )
    return ext


@pytest.fixture
def pipeline(mock_regex_extractor, mock_llm_extractor):
    return ApartmentExtractionPipeline(
        regex_extractor=mock_regex_extractor,
        llm_extractor=mock_llm_extractor,
        redis=None,  # no cache in tests
    )


class TestPipelineHighConfidence:
    @pytest.mark.asyncio
    async def test_regex_only_no_llm_call(self, pipeline, mock_llm_extractor):
        result = await pipeline.extract("двушка премьер форт до 100к")
        assert result.meta.source == "regex"
        mock_llm_extractor.extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_high_confidence_has_filters(self, pipeline):
        result = await pipeline.extract("двушка премьер форт до 100к")
        assert result.hard.rooms == 2
        assert result.hard.complex_name == "Premier Fort Beach"
        assert result.hard.max_price_eur == 100000


class TestPipelineMediumConfidence:
    @pytest.mark.asyncio
    async def test_medium_calls_llm(self, pipeline, mock_llm_extractor):
        result = await pipeline.extract("двушка до 100к")  # no city/complex → MEDIUM
        mock_llm_extractor.extract.assert_called_once()
        assert result.meta.source == "hybrid"


class TestPipelineLowConfidence:
    @pytest.mark.asyncio
    async def test_low_calls_llm_full(self, pipeline, mock_llm_extractor):
        result = await pipeline.extract("что-нибудь просторное у моря")
        mock_llm_extractor.extract.assert_called_once()
        # partial_filters should be None for LOW confidence
        call_kwargs = mock_llm_extractor.extract.call_args
        assert call_kwargs.kwargs.get("partial_filters") is None


class TestPipelineCityExtraction:
    @pytest.mark.asyncio
    async def test_city_extracted_by_regex(self, pipeline, mock_llm_extractor):
        result = await pipeline.extract("двушка солнечный берег до 100к")
        assert result.hard.city == "Солнечный берег"
        assert result.meta.source == "regex"
        mock_llm_extractor.extract.assert_not_called()
```

**Step 2: Run to verify fail**

Run: `uv run pytest tests/unit/services/test_apartment_extraction_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement pipeline orchestrator**

```python
# telegram_bot/services/apartment_extraction_pipeline.py
"""Apartment extraction pipeline: normalizer → regex → confidence gate → LLM fallback."""

from __future__ import annotations

import hashlib
import logging
from typing import TYPE_CHECKING

from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
    SoftPreferences,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from telegram_bot.services.apartment_llm_extractor import ApartmentLlmExtractor

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "extraction:v1:"
_CACHE_TTL = 86400  # 24h


class ApartmentExtractionPipeline:
    """Orchestrates regex → confidence gate → LLM fallback."""

    def __init__(
        self,
        regex_extractor: ApartmentFilterExtractor,
        llm_extractor: ApartmentLlmExtractor | None = None,
        redis: Redis | None = None,
    ) -> None:
        self._regex = regex_extractor
        self._llm = llm_extractor
        self._redis = redis

    async def extract(self, query: str) -> ApartmentSearchFilters:
        """Main entry point: regex → confidence gate → LLM fallback."""
        # 1. Check cache
        cached = await self._cache_get(query)
        if cached:
            return cached

        # 2. Regex extraction
        parsed = self._regex.parse(query)
        regex_result = self._parsed_to_search_filters(parsed)

        # 3. Confidence gate
        if regex_result.meta.confidence == "HIGH":
            return regex_result

        if self._llm is None:
            return regex_result  # no LLM available, return regex result as-is

        if regex_result.meta.confidence == "MEDIUM":
            llm_result = await self._llm.extract(
                query=query, partial_filters=regex_result.hard
            )
            from telegram_bot.services.apartment_llm_extractor import (
                merge_extraction_results,
            )
            merged = merge_extraction_results(regex_result, llm_result)
            await self._cache_set(query, merged)
            return merged

        # LOW — full LLM extraction
        llm_result = await self._llm.extract(query=query)
        await self._cache_set(query, llm_result)
        return llm_result

    def _parsed_to_search_filters(self, parsed) -> ApartmentSearchFilters:
        """Convert legacy ApartmentQueryParseResult to ApartmentSearchFilters."""
        hard = HardFilters(
            city=getattr(parsed, "city", None),
            complex_name=parsed.complex_name,
            rooms=parsed.rooms,
            min_price_eur=parsed.min_price_eur,
            max_price_eur=parsed.max_price_eur,
            min_area_m2=parsed.min_area_m2,
            max_area_m2=parsed.max_area_m2,
            min_floor=parsed.min_floor,
            max_floor=parsed.max_floor,
            view_tags=parsed.view_tags or None,
            is_furnished=parsed.is_furnished,
        )
        return ApartmentSearchFilters(
            hard=hard,
            soft=SoftPreferences(),
            meta=ExtractionMeta(
                source="regex",
                confidence=parsed.confidence,
                score=parsed.score,
                conflicts=parsed.conflicts,
                missing_fields=getattr(parsed, "missing_fields", []),
                normalized_query=parsed.raw_query,
                semantic_remainder=parsed.semantic_query,
            ),
        )

    async def _cache_get(self, query: str) -> ApartmentSearchFilters | None:
        if not self._redis:
            return None
        key = _CACHE_PREFIX + hashlib.sha256(query.lower().encode()).hexdigest()[:16]
        data = await self._redis.get(key)
        if data:
            return ApartmentSearchFilters.model_validate_json(data)
        return None

    async def _cache_set(self, query: str, result: ApartmentSearchFilters) -> None:
        if not self._redis or result.meta.source == "regex":
            return
        key = _CACHE_PREFIX + hashlib.sha256(query.lower().encode()).hexdigest()[:16]
        await self._redis.set(key, result.model_dump_json(), ex=_CACHE_TTL)
```

**Step 4: Run tests**

Run: `uv run pytest tests/unit/services/test_apartment_extraction_pipeline.py -v`
Expected: All PASS

**Step 5: Run full check**

Run: `make check && uv run pytest tests/unit/services/ -v -k apartment`
Expected: All PASS

**Step 6: Commit**

```bash
git add telegram_bot/services/apartment_extraction_pipeline.py tests/unit/services/test_apartment_extraction_pipeline.py
git commit -m "feat(apartments): add extraction pipeline orchestrator with confidence gate"
```

---

## Task 6: Wire pipeline into bot.py fast path

**Files:**
- Modify: `telegram_bot/bot.py` (lines ~2212-2330)
- Modify: `tests/unit/test_bot_handlers.py` (or relevant bot test file)

**Step 1: Update bot.py initialization**

In `PropertyBot.__init__()` (after line ~369, after `_apartments_service`):

```python
from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor
from telegram_bot.services.apartment_extraction_pipeline import ApartmentExtractionPipeline

self._apartment_extractor = ApartmentFilterExtractor()

# LLM extractor — optional, only if LLM available
self._apartment_llm_extractor: ApartmentLlmExtractor | None = None
try:
    from telegram_bot.services.apartment_llm_extractor import ApartmentLlmExtractor
    self._apartment_llm_extractor = ApartmentLlmExtractor(
        llm=self._llm, model=config.supervisor_model
    )
except Exception:
    logger.warning("Apartment LLM extractor not available, regex-only mode")

self._apartment_pipeline = ApartmentExtractionPipeline(
    regex_extractor=self._apartment_extractor,
    llm_extractor=self._apartment_llm_extractor,
    redis=getattr(self._cache, "_redis", None),
)
```

**Step 2: Update `_handle_apartment_fast_path()`**

Replace the current filter extraction block (lines ~2220-2224) with:

```python
# Extract filters via pipeline (regex → confidence gate → LLM fallback)
search_filters = await self._apartment_pipeline.extract(user_text)
filters = search_filters.hard.to_filters_dict()
semantic_query = search_filters.build_semantic_query()
confidence = search_filters.meta.confidence

# LOW confidence with no LLM → escalate
if confidence == "LOW" and self._apartment_llm_extractor is None:
    return None
```

Replace `parsed.semantic_query` with `semantic_query` in the embedding call.
Replace `parsed.confidence` with `confidence` in `check_escalation()`.

**Step 3: Add Langfuse scores**

After successful search, add extraction metrics:

```python
lf = get_client()
lf.score(
    name="extraction_source",
    value=search_filters.meta.source,
    data_type="CATEGORICAL",
)
lf.score(
    name="extraction_confidence",
    value=search_filters.meta.confidence,
    data_type="CATEGORICAL",
)
```

**Step 4: Run existing tests**

Run: `uv run pytest tests/unit/test_bot_handlers.py -v -k apartment`
Expected: PASS (existing tests should still work since the output format is compatible)

**Step 5: Run full test suite**

Run: `make check && uv run pytest tests/unit/ -n auto`
Expected: All PASS

**Step 6: Commit**

```bash
git add telegram_bot/bot.py
git commit -m "feat(apartments): wire extraction pipeline into bot fast path"
```

---

## Task 7: Update apartment_tools.py agent tool

**Files:**
- Modify: `telegram_bot/agents/apartment_tools.py`
- Modify: `tests/unit/agents/test_apartment_tools.py`

**Step 1: Update agent tool to use pipeline**

The `apartment_search` @tool in `apartment_tools.py` currently builds filters manually from kwargs. Update it to also accept free-text extraction via the pipeline when the agent passes a complex query.

Add pipeline extraction as a fallback when no explicit filter kwargs are provided:

```python
# At the top of apartment_search(), after getting ctx:
if not any([rooms, min_price_eur, max_price_eur, min_area_m2, max_area_m2,
            min_floor, max_floor, complex_name, view, is_furnished]):
    # No explicit filters — extract from query text
    pipeline = getattr(ctx, "apartment_pipeline", None)
    if pipeline:
        search_filters = await pipeline.extract(query)
        filters = search_filters.hard.to_filters_dict()
        query = search_filters.build_semantic_query()
```

**Step 2: Run existing agent tests**

Run: `uv run pytest tests/unit/agents/test_apartment_tools.py -v`
Expected: All PASS

**Step 3: Commit**

```bash
git add telegram_bot/agents/apartment_tools.py tests/unit/agents/test_apartment_tools.py
git commit -m "feat(apartments): use extraction pipeline in agent tool fallback"
```

---

## Task 8: End-to-end integration test

**Files:**
- Create: `tests/unit/services/test_apartment_extraction_e2e.py`

**Step 1: Write integration tests**

```python
# tests/unit/services/test_apartment_extraction_e2e.py
"""End-to-end tests for apartment extraction pipeline (regex path only, no LLM)."""

import pytest

from telegram_bot.services.apartment_extraction_pipeline import ApartmentExtractionPipeline
from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor


@pytest.fixture
def pipeline():
    return ApartmentExtractionPipeline(
        regex_extractor=ApartmentFilterExtractor(),
        llm_extractor=None,
        redis=None,
    )


@pytest.mark.parametrize(
    ("query", "expected_city", "expected_rooms", "expected_max_price", "expected_confidence"),
    [
        ("двушка солнечный берег до 100к", "Солнечный берег", 2, 100000, "HIGH"),
        ("студия в премьер форте", None, 1, None, "HIGH"),  # complex counts as entity
        ("трешка свети влас от 50к до 200к", "Свети Влас", 3, 200000, "HIGH"),
        ("двушка до 100к", None, 2, 100000, "MEDIUM"),  # no city → MEDIUM
        ("апартамент элените", "Элените", None, None, "MEDIUM"),  # city only
        ("что-нибудь просторное", None, None, None, "LOW"),  # nothing extracted
    ],
)
@pytest.mark.asyncio
async def test_extraction_e2e(
    pipeline, query, expected_city, expected_rooms, expected_max_price, expected_confidence
):
    result = await pipeline.extract(query)
    assert result.hard.city == expected_city
    assert result.hard.rooms == expected_rooms
    assert result.hard.max_price_eur == expected_max_price
    assert result.meta.confidence == expected_confidence


@pytest.mark.asyncio
async def test_filters_dict_compatible_with_qdrant(pipeline):
    """Verify to_filters_dict() output is compatible with _build_apartment_filter()."""
    result = await pipeline.extract("двушка солнечный берег до 100к")
    d = result.hard.to_filters_dict()
    assert d is not None
    assert d["city"] == "Солнечный берег"
    assert d["rooms"] == 2
    assert d["price_eur"]["lte"] == 100000


@pytest.mark.asyncio
async def test_semantic_query_strips_filters(pipeline):
    result = await pipeline.extract("уютная двушка солнечный берег до 100к")
    sq = result.build_semantic_query()
    assert "солнечный берег" not in sq.lower()
    assert "100" not in sq
```

**Step 2: Run tests**

Run: `uv run pytest tests/unit/services/test_apartment_extraction_e2e.py -v`
Expected: All PASS

**Step 3: Run full suite**

Run: `make check && uv run pytest tests/unit/ -n auto`
Expected: All PASS

**Step 4: Commit**

```bash
git add tests/unit/services/test_apartment_extraction_e2e.py
git commit -m "test(apartments): add e2e extraction pipeline tests"
```

---

## Summary

| Task | Description | New/Modified Files | Estimated |
|------|------------|-------------------|-----------|
| 1 | Pydantic models | apartment_models.py + test | ~15 min |
| 2 | City aliases + extraction | apartment_filter_extractor.py + test | ~10 min |
| 3 | 3-level confidence | apartment_models.py + test | ~10 min |
| 4 | Instructor LLM extractor | apartment_llm_extractor.py + test + pyproject.toml | ~15 min |
| 5 | Pipeline orchestrator | apartment_extraction_pipeline.py + test | ~15 min |
| 6 | Wire into bot.py | bot.py | ~10 min |
| 7 | Update agent tool | apartment_tools.py | ~5 min |
| 8 | E2E tests | test_apartment_extraction_e2e.py | ~10 min |

**Total: 8 tasks, ~90 min**

**Dependencies:** Task 1 → Tasks 2,3 → Task 4 → Task 5 → Tasks 6,7 → Task 8
