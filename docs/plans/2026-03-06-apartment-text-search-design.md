# Design: Текстовый поиск апартаментов (Instructor + Hybrid Extraction)

**Дата:** 2026-03-06
**Статус:** Draft
**Автор:** Claude (brainstorming session)

## Проблема

Текущий `ApartmentFilterExtractor` (regex-only):
- Не знает городов ("солнечный берег" → не извлекается, хотя `city` indexed в Qdrant)
- Ломается на свободных формулировках ("просторная у моря недорого")
- Бинарная confidence (HIGH/LOW) без промежуточного уровня
- Нет разделения hard_filters / soft_preferences — "у моря" ставит жесткий `view_tags=["sea"]`, хотя это предпочтение
- При LOW confidence всё уходит в agent (дорого, медленно)

## Решение: 3-tier extraction pipeline

```
User query
    |
    v
[1. Normalizer] — алиасы городов, комплексов, транслитерация, "двушка"→2, "к"→000
    |
    v
[2. Regex Parser] — цены, комнаты, площадь, этаж, город, комплекс, вид (улучшенный)
    |
    v
[3. Confidence Gate] — HIGH → skip LLM | MEDIUM → LLM доизвлечение | LOW → full LLM
    |
    v
[4. Instructor + gpt-4o-mini] — structured extraction для unresolved slots
    |
    v
[5. Post-normalization] — валидация, auto-fix конфликтов, каноникализация
    |
    v
[6. ApartmentSearchFilters] — единая Pydantic-модель → Qdrant filter + semantic query
```

## Данные в Qdrant (текущее состояние)

- **297 апартаментов**, коллекция `apartments`
- **3 города:** Солнечный берег (258), Свети Влас (35), Элените (4)
- **10 комплексов:** Premier Fort Beach, Prestige Fort Beach, Green Fort Suites и т.д.
- **Векторы:** dense(1024, BGE-M3) + sparse(BM42, IDF) + ColBERT(1024, MaxSim)
- **Payload-индексы (11):** city, complex_name, rooms, price_eur, area_m2, floor, view_primary, view_tags, section, is_furnished, is_promotion

## Pydantic-модель фильтров

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


# --- Hard Filters (Qdrant payload filter) ---

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
        if self.min_floor is not None and self.max_floor is not None and self.min_floor > self.max_floor:
            self.min_floor, self.max_floor = self.max_floor, self.min_floor
        return self


# --- Soft Preferences (влияют на rerank/semantic, не на filter) ---

class SoftPreferences(BaseModel):
    """Мягкие предпочтения — boosting в semantic search, не отсекают результаты."""
    near_sea: bool = Field(False, description="Близко к морю (не обязательно вид на море)")
    spacious: bool = Field(False, description="Просторная")
    budget_friendly: bool = Field(False, description="Недорого/бюджетно")
    high_floor: bool = Field(False, description="Высокий этаж")
    quiet: bool = Field(False, description="Тихое место")
    sort_bias: Literal["price_asc", "price_desc", "area_desc", "floor_desc", "relevance"] = "relevance"


# --- Extraction Meta ---

class ExtractionMeta(BaseModel):
    """Метаданные извлечения для мониторинга и отладки."""
    source: Literal["regex", "llm", "hybrid"] = "regex"
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    score: int = 0
    missing_fields: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    normalized_query: str = ""
    semantic_remainder: str = ""


# --- Top-level result ---

class ApartmentSearchFilters(BaseModel):
    """Полный результат extraction pipeline."""
    hard: HardFilters = Field(default_factory=HardFilters)
    soft: SoftPreferences = Field(default_factory=SoftPreferences)
    meta: ExtractionMeta = Field(default_factory=ExtractionMeta)
```

## Словарь алиасов городов

```python
_CITY_ALIASES: dict[str, str] = {
    # Солнечный берег
    "солнечный берег": "Солнечный берег",
    "солнечный": "Солнечный берег",
    "sunny beach": "Солнечный берег",
    "слънчев бряг": "Солнечный берег",
    "санни бич": "Солнечный берег",
    # Свети Влас
    "свети влас": "Свети Влас",
    "святой влас": "Свети Влас",
    "св влас": "Свети Влас",
    "sv vlas": "Свети Влас",
    "sveti vlas": "Свети Влас",
    "saint vlas": "Свети Влас",
    # Элените
    "элените": "Элените",
    "elenite": "Элените",
    "елените": "Элените",
}
```

## Confidence Gate (3 уровня)

| Confidence | Условие | Действие |
|-----------|---------|----------|
| **HIGH** | >= 2 hard filters + >= 1 entity (city/complex) | Skip LLM, прямой поиск |
| **MEDIUM** | >= 1 hard filter, но missing critical slot (city/rooms/price) | LLM доизвлечение только для unresolved slots |
| **LOW** | 0 hard filters или конфликты | Full LLM extraction |

**Critical slots** (хотя бы 1 из 3 должен быть заполнен для MEDIUM+):
- `city` или `complex_name` (где ищем)
- `rooms` (что ищем)
- `price` range (бюджет)

## Instructor Integration

```python
import instructor
from instructor.cache import AutoCache
from openai import AsyncOpenAI

# Инициализация (один раз в bot.py)
_llm = AsyncOpenAI(base_url=config.litellm_url, api_key=config.api_key)
_instructor_client = instructor.from_openai(_llm)
_cache = AutoCache(maxsize=500)

# Системный промпт
EXTRACTION_SYSTEM_PROMPT = """Ты извлекаешь фильтры поиска апартаментов из запроса пользователя.

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

# Вызов (только для MEDIUM/LOW confidence)
async def extract_with_llm(
    query: str,
    partial_filters: HardFilters | None = None,
) -> ApartmentSearchFilters:
    """LLM extraction для unresolved slots."""
    context = ""
    if partial_filters:
        filled = {k: v for k, v in partial_filters.model_dump().items() if v is not None}
        context = f"\nУже извлечено regex: {filled}\nДоизвлеки остальное."

    result = await _instructor_client.chat.completions.create(
        model="gpt-4o-mini",
        response_model=ApartmentSearchFilters,
        max_retries=2,
        messages=[
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": query + context},
        ],
    )
    result.meta.source = "hybrid" if partial_filters else "llm"
    return result
```

## Router-логика (полный flow)

```python
async def extract_apartment_filters(query: str) -> ApartmentSearchFilters:
    """Main entry point: normalizer → regex → confidence gate → LLM fallback."""

    # 1. Normalize
    normalized = normalize_query(query)  # алиасы, транслитерация, "к"→"000"

    # 2. Regex extraction (улучшенный — с городами)
    regex_result = regex_extractor.parse(normalized)

    # 3. Confidence gate
    if regex_result.meta.confidence == "HIGH":
        return regex_result  # 0 LLM calls

    if regex_result.meta.confidence == "MEDIUM":
        # LLM доизвлечение только missing slots
        llm_result = await extract_with_llm(query, partial_filters=regex_result.hard)
        return merge_results(regex_result, llm_result)

    # LOW — full LLM extraction
    return await extract_with_llm(query)


def merge_results(
    regex: ApartmentSearchFilters,
    llm: ApartmentSearchFilters,
) -> ApartmentSearchFilters:
    """Regex wins для числовых полей, LLM wins для текстовых/preferences."""
    merged_hard = {}
    for field_name in HardFilters.model_fields:
        regex_val = getattr(regex.hard, field_name)
        llm_val = getattr(llm.hard, field_name)
        # Regex приоритет для числовых (точнее), LLM для текстовых
        merged_hard[field_name] = regex_val if regex_val is not None else llm_val

    return ApartmentSearchFilters(
        hard=HardFilters(**merged_hard),
        soft=llm.soft,  # LLM лучше понимает preferences
        meta=ExtractionMeta(
            source="hybrid",
            confidence=max(regex.meta.confidence, llm.meta.confidence),
            normalized_query=regex.meta.normalized_query,
            semantic_remainder=regex.meta.semantic_remainder,
        ),
    )
```

## Построение Qdrant-фильтра

```python
def build_qdrant_filter(hard: HardFilters) -> dict | None:
    """HardFilters → dict для _build_apartment_filter()."""
    filters: dict = {}
    if hard.city:
        filters["city"] = hard.city
    if hard.complex_name:
        filters["complex_name"] = hard.complex_name
    if hard.rooms:
        filters["rooms"] = hard.rooms
    if hard.min_price_eur is not None or hard.max_price_eur is not None:
        price_range: dict = {}
        if hard.min_price_eur is not None:
            price_range["gte"] = hard.min_price_eur
        if hard.max_price_eur is not None:
            price_range["lte"] = hard.max_price_eur
        filters["price_eur"] = price_range
    # ... аналогично для area_m2, floor, view_tags, is_furnished
    return filters or None
```

## Semantic query из preferences

```python
def build_semantic_query(soft: SoftPreferences, remainder: str) -> str:
    """SoftPreferences → дополнение к semantic query для vector search."""
    parts = []
    if remainder:
        parts.append(remainder)
    if soft.near_sea:
        parts.append("близко к морю")
    if soft.spacious:
        parts.append("просторная квартира")
    if soft.quiet:
        parts.append("тихое спокойное место")
    return " ".join(parts) if parts else "апартамент"
```

## Кэширование

```python
# Redis cache для LLM extractions
# Key: extraction:v1:{sha256(normalized_query)}
# Value: ApartmentSearchFilters.model_dump_json()
# TTL: 24h (цены могут измениться, но фильтры стабильны)

async def cached_extract(query: str) -> ApartmentSearchFilters | None:
    key = f"extraction:v1:{hashlib.sha256(query.encode()).hexdigest()[:16]}"
    cached = await redis.get(key)
    if cached:
        return ApartmentSearchFilters.model_validate_json(cached)
    return None

async def store_extraction(query: str, result: ApartmentSearchFilters) -> None:
    if result.meta.source in ("llm", "hybrid"):  # кэшируем только LLM результаты
        key = f"extraction:v1:{hashlib.sha256(query.encode()).hexdigest()[:16]}"
        await redis.set(key, result.model_dump_json(), ex=86400)
```

## Примеры запросов

| Запрос | Tier | Результат |
|--------|------|-----------|
| "двушка солнечный берег до 100 000" | Regex → HIGH | `{rooms:2, city:"Солнечный берег", max_price:100000}` |
| "студия в премьер форте" | Regex → HIGH | `{rooms:1, complex:"Premier Fort Beach"}` |
| "что-нибудь просторное у моря недорого" | Regex → LOW → LLM | `hard:{min_area:60}, soft:{near_sea, budget_friendly, sort:price_asc}` |
| "трешка с панорамным видом не дороже 200к" | Regex → MEDIUM → LLM для soft | `hard:{rooms:3, max_price:200000, view:["sea","panorama"]}, soft:{}` |
| "апартамент Свети Влас высокий этаж" | Regex → MEDIUM | `hard:{city:"Свети Влас", min_floor:4}, soft:{high_floor}` |

## Мониторинг (Langfuse)

| Score | Type | Описание |
|-------|------|----------|
| `extraction_source` | CATEGORICAL | regex / llm / hybrid |
| `extraction_confidence` | CATEGORICAL | HIGH / MEDIUM / LOW |
| `extraction_latency_ms` | NUMERIC | Время extraction pipeline |
| `llm_extraction_cost` | NUMERIC | Стоимость LLM вызова (из LiteLLM) |
| `filters_count` | NUMERIC | Количество извлеченных hard фильтров |

## Зависимости

```toml
# pyproject.toml
[project.dependencies]
instructor = ">=1.7.0"
# Всё остальное уже есть: pydantic, openai, qdrant-client, redis
```

## Изменяемые файлы

| Файл | Изменение |
|------|-----------|
| `telegram_bot/services/apartment_filter_extractor.py` | Рефакторинг: добавить города, вернуть `ApartmentSearchFilters` |
| `telegram_bot/services/apartment_models.py` | Новые модели: `HardFilters`, `SoftPreferences`, `ExtractionMeta`, `ApartmentSearchFilters` |
| `telegram_bot/services/apartment_llm_extractor.py` | **Новый файл:** Instructor integration |
| `telegram_bot/services/apartments_service.py` | Принимать `ApartmentSearchFilters` вместо raw dict |
| `telegram_bot/bot.py` | Инициализация Instructor client |
| `telegram_bot/agents/apartment_tools.py` | Использовать новый extraction pipeline |
| `pyproject.toml` | Добавить `instructor` dependency |

## Обратная совместимость

- `ApartmentQueryParseResult` остается, но deprecated
- `ApartmentSearchFilters.hard.to_filters_dict()` возвращает тот же формат dict, что и `ApartmentQueryParseResult.to_filters_dict()`
- Funnel dialog продолжает работать — его фильтры строятся из dialog_data, не из text extraction

## Риски

| Риск | Митигация |
|------|-----------|
| LLM hallucинирует несуществующий город | Post-validation: проверка city в `_CITY_ALIASES.values()` |
| Instructor не работает с LiteLLM | Fallback: raw OpenAI tool_use без Instructor |
| Latency LLM > 500ms | Cache + confidence gate (70% запросов = regex only) |
| Cost на LLM extraction | gpt-4o-mini ~$0.0001/запрос, cache hit rate ~50% |
