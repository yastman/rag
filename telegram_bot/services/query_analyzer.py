"""Query analyzer service using LLM to extract filters.

Uses OpenAI SDK via Langfuse drop-in replacement for auto-tracing.
"""

import json
import logging
from typing import Any

import openai
from langfuse.openai import AsyncOpenAI

from telegram_bot.integrations.prompt_manager import get_prompt


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

    async def analyze(self, query: str) -> dict[str, Any]:
        """Analyze query and extract filters + semantic query.

        Args:
            query: User query text

        Returns:
            Dict with 'filters' and 'semantic_query'
        """
        try:
            system_prompt = get_prompt("query-analysis", fallback=SYSTEM_PROMPT)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Запрос пользователя: {query}"},
                ],
                response_format={"type": "json_object"},  # type: ignore[arg-type]
                temperature=0.0,
                max_tokens=1000,
                name="query-analysis",  # type: ignore[call-overload]  # langfuse kwarg
            )

            content = response.choices[0].message.content

            if content is None:
                logger.warning(
                    "QueryAnalyzer: LLM returned None content. model=%s",
                    self.model,
                )
                return {"filters": {}, "semantic_query": query}

            try:
                analysis = json.loads(content)
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(
                    "QueryAnalyzer: failed to parse JSON: %s. Raw: %s",
                    e,
                    content[:500],
                )
                return {"filters": {}, "semantic_query": query}

            if not isinstance(analysis, dict):
                logger.warning(
                    "QueryAnalyzer: non-dict JSON: type=%s",
                    type(analysis).__name__,
                )
                return {"filters": {}, "semantic_query": query}

            filters = analysis.get("filters", {})
            semantic_query = analysis.get("semantic_query", query)

            logger.info("QueryAnalyzer: filters=%s, semantic_query=%s", filters, semantic_query)
            return {"filters": filters, "semantic_query": semantic_query}

        except (openai.APIConnectionError, openai.RateLimitError, openai.APITimeoutError) as e:
            logger.error("QueryAnalyzer API error: %s", e)
            return {"filters": {}, "semantic_query": query}
        except Exception as e:
            logger.error("QueryAnalyzer error: %s", e, exc_info=True)
            return {"filters": {}, "semantic_query": query}

    async def close(self):
        """Close the OpenAI client."""
        await self.client.close()
