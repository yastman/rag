"""Instructor-based LLM extractor for apartment search filters."""

from __future__ import annotations

import logging

import instructor
from openai import AsyncOpenAI

from telegram_bot.integrations.prompt_manager import get_prompt
from telegram_bot.observability import observe
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    HardFilters,
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
- "двушка" = 2 комнаты, "трешка" = 3 комнаты, "студия" = 1 комната
- "у моря" = near_sea preference, НЕ view_tags (если не сказано "вид на море")
- "недорого"/"бюджетно" = budget_friendly preference + sort_bias="price_asc"
- "просторная" = spacious preference + min_area_m2 >= 60
- Если не уверен — оставь None, не выдумывай"""


def _get_system_prompt() -> str:
    """Fetch system prompt from Langfuse Prompt Management with fallback to default.

    Prompt name: "apartment-extraction-system-prompt"
    Falls back to EXTRACTION_SYSTEM_PROMPT when Langfuse is unavailable.
    """
    return get_prompt(
        "apartment-extraction-system-prompt",
        fallback=EXTRACTION_SYSTEM_PROMPT,
    )


def merge_extraction_results(
    regex: ApartmentSearchFilters, llm: ApartmentSearchFilters
) -> ApartmentSearchFilters:
    """Merge regex and LLM results. Regex wins for numeric fields; LLM fills gaps."""
    r = regex.hard
    lh = llm.hard

    merged_hard = HardFilters(
        city=r.city if r.city is not None else lh.city,
        complex_name=r.complex_name if r.complex_name is not None else lh.complex_name,
        rooms=r.rooms if r.rooms is not None else lh.rooms,
        min_price_eur=r.min_price_eur if r.min_price_eur is not None else lh.min_price_eur,
        max_price_eur=r.max_price_eur if r.max_price_eur is not None else lh.max_price_eur,
        min_area_m2=r.min_area_m2 if r.min_area_m2 is not None else lh.min_area_m2,
        max_area_m2=r.max_area_m2 if r.max_area_m2 is not None else lh.max_area_m2,
        min_floor=r.min_floor if r.min_floor is not None else lh.min_floor,
        max_floor=r.max_floor if r.max_floor is not None else lh.max_floor,
        view_tags=r.view_tags or lh.view_tags,
        section=r.section if r.section is not None else lh.section,
        is_furnished=r.is_furnished if r.is_furnished is not None else lh.is_furnished,
    )

    return ApartmentSearchFilters(
        hard=merged_hard,
        soft=llm.soft,
        meta=llm.meta.model_copy(update={"source": "hybrid"}),
    )


class ApartmentLlmExtractor:
    """Instructor-based structured extraction from natural language queries."""

    def __init__(self, llm: AsyncOpenAI, model: str = "gpt-4o-mini") -> None:
        self._client = instructor.from_openai(llm)
        self._model = model

    @observe(name="apartment-llm-extract", capture_input=False, capture_output=False)
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

        source = "hybrid" if partial_filters else "llm"
        messages = [
            {"role": "system", "content": _get_system_prompt() + context},
            {"role": "user", "content": query},
        ]

        result: ApartmentSearchFilters = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            response_model=ApartmentSearchFilters,
            max_retries=2,
        )

        # Post-validation: clear city if not in our valid set
        if result.hard.city is not None and result.hard.city not in _VALID_CITIES:
            result = result.model_copy(
                update={"hard": result.hard.model_copy(update={"city": None})}
            )

        # Set extraction source
        return result.model_copy(update={"meta": result.meta.model_copy(update={"source": source})})
