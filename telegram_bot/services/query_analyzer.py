"""Query analyzer service using LLM to extract filters.

Uses OpenAI SDK via Langfuse drop-in replacement for auto-tracing.
"""

import logging
import warnings
from typing import Any

import instructor
import openai
from langfuse.openai import AsyncOpenAI
from pydantic import BaseModel, Field

from telegram_bot.integrations.prompt_manager import get_prompt
from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Ты QueryAnalyzer для системы поиска недвижимости.
Твоя задача: извлечь структурированные фильтры и семантический запрос из текста пользователя.

ДОСТУПНЫЕ ФИЛЬТРЫ:
- price (integer): цена в евро, операторы: lt, lte, gt, gte
- rooms (integer): количество комнат (1, 2, 3, ...)
- city (string): город ("Солнечный берег", "Несебр", "Бургас", "Варна")
- area (float): площадь в м², операторы: lt, lte, gt, gte
- floor (integer): этаж
- distance_to_sea (integer): расстояние до моря в метрах, операторы: lt, lte, gt, gte
- maintenance (float): стоимость поддержки в евро, операторы: lt, lte, gt, gte
- bathrooms (integer): количество санузлов
- furniture (string): "Есть" (если упомянута мебель)
- year_round (string): "Да" (если упомянута круглогодичность)

ФОРМАТ ОТВЕТА (строгий JSON):
{
  "filters": {
    "price": {"lt": 100000},
    "city": "Несебр",
    "rooms": 2
  },
  "semantic_query": "уютная квартира с хорошим ремонтом"
}

ПРАВИЛА:
1. Извлекай ТОЛЬКО упомянутые фильтры
2. semantic_query - суть запроса БЕЗ числовых условий (для embedding)
3. Если фильтров нет - верни пустой объект filters: {}
4. ОБЯЗАТЕЛЬНО возвращай валидный JSON"""


class QueryAnalysisResult(BaseModel):
    """Pydantic model for query analysis extraction via Instructor."""

    filters: dict[str, Any] = Field(
        default_factory=dict,
        description="Extracted filters from user query",
    )
    semantic_query: str = Field(
        default="",
        description="Semantic query for embedding search",
    )


class QueryAnalyzer:
    """Analyze user queries to extract structured filters and semantic query."""

    def __init__(self, api_key: str, base_url: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
            max_retries=2,
            timeout=30.0,
        )
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=("Client should be an instance of openai.OpenAI or openai.AsyncOpenAI.*"),
                category=UserWarning,
            )
            self._instructor_client = instructor.from_openai(self.client)

    @observe(
        name="query-analyzer",
        capture_input=False,
        capture_output=False,
    )
    async def analyze(self, query: str) -> dict[str, Any]:
        """Analyze query and extract filters + semantic query.

        Wrapped in ``@observe`` (***REMOVED***1659) so the auto-traced generation
        produced by ``langfuse.openai`` (preserved through
        ``instructor.from_openai`` — the underlying client's
        ``chat.completions.create`` retains the wrapt langfuse marker, see
        the preflight test ``TestQueryAnalyzerInstructorLangfuseCompat``)
        becomes a child of a named ``query-analyzer`` span instead of an
        orphan top-level trace when the analyzer is invoked outside a
        request-scoped trace.

        Per the audit comment on ***REMOVED***1659 the wrapper is a *plain span*, not
        ``as_type="generation"``: ``langfuse.openai`` already emits a
        generation observation for each ``chat.completions.create`` call
        and an outer generation would produce duplicate observations.

        Curated ``update_current_span`` payloads avoid leaking the full
        query or the full LLM response into Langfuse:

        * input: ``{"query_preview": query[:120], "model": self.model}``
        * output: ``{"filter_keys": sorted(filters.keys()),
          "filter_count": len(filters),
          "semantic_query_len": len(semantic_query)}``
          — schema-level metadata only; no filter *values*, no semantic
          query *content*.
        * on exception: ``level="ERROR"`` with ``status_message`` truncated
          to 200 chars; existing fallback contract preserved (returns
          ``{"filters": {}, "semantic_query": query}``).

        Args:
            query: User query text

        Returns:
            Dict with 'filters' and 'semantic_query'
        """
        lf = get_client()
        if lf is not None:
            lf.update_current_span(
                input={
                    "query_preview": query[:120],
                    "model": self.model,
                }
            )
        try:
            system_prompt = get_prompt("query-analysis", fallback=SYSTEM_PROMPT)
            result = await self._instructor_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Запрос пользователя: {query}"},
                ],
                response_model=QueryAnalysisResult,
                max_retries=2,
                temperature=0.0,
                max_tokens=1000,
                name="query-analysis",  ***REMOVED*** type: ignore[call-overload]  ***REMOVED*** langfuse kwarg
            )

            filters = result.filters
            semantic_query = result.semantic_query or query

            if lf is not None:
                lf.update_current_span(
                    output={
                        "filter_keys": sorted(filters.keys()),
                        "filter_count": len(filters),
                        "semantic_query_len": len(semantic_query),
                    }
                )

            logger.info("QueryAnalyzer: filters=%s, semantic_query=%s", filters, semantic_query)
            return {"filters": filters, "semantic_query": semantic_query}

        except (openai.APIConnectionError, openai.RateLimitError, openai.APITimeoutError) as e:
            logger.error("QueryAnalyzer API error: %s", e)
            if lf is not None:
                lf.update_current_span(level="ERROR", status_message=str(e)[:200])
            return {"filters": {}, "semantic_query": query}
        except Exception as e:
            logger.error("QueryAnalyzer error: %s", e, exc_info=True)
            if lf is not None:
                lf.update_current_span(level="ERROR", status_message=str(e)[:200])
            return {"filters": {}, "semantic_query": query}

    async def close(self):
        """Close the OpenAI client."""
        await self.client.close()
