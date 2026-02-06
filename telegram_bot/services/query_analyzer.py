"""Query analyzer service using LLM to extract filters."""

import json
import logging
from typing import Any

import httpx

from telegram_bot.observability import get_client, observe


logger = logging.getLogger(__name__)


class QueryAnalyzer:
    """Analyze user queries to extract structured filters and semantic query."""

    def __init__(self, api_key: str, base_url: str, model: str = "gpt-4o-mini"):
        """Initialize query analyzer.

        Args:
            api_key: OpenAI API key
            base_url: API base URL
            model: Model to use (default: gpt-4o-mini for cost efficiency)
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.client = httpx.AsyncClient(timeout=30.0)

    @observe(name="query-analyzer", as_type="generation")
    async def analyze(self, query: str) -> dict[str, Any]:
        """
        Analyze query and extract filters + semantic query.

        Args:
            query: User query text

        Returns:
            Dict with 'filters' and 'semantic_query'
            Example: {
                "filters": {"price": {"lt": 100000}, "city": "Несебр"},
                "semantic_query": "недорогие квартиры с хорошим ремонтом"
            }
        """
        langfuse = get_client()

        # Track at start
        langfuse.update_current_generation(
            input={"query_preview": query[:100]},
            model=self.model,
        )

        system_prompt = """Ты QueryAnalyzer для системы поиска недвижимости в Болгарии.
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

        user_prompt = f"Запрос пользователя: {query}"

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.0,
                    "max_tokens": 1000,  # GLM-4.7 needs more for thinking mode
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # Guard against None content (some models return null in thinking mode)
            if content is None:
                logger.warning(
                    "QueryAnalyzer: LLM returned None content. finish_reason=%s, model=%s",
                    result["choices"][0].get("finish_reason", "unknown"),
                    result.get("model", self.model),
                )
                return {"filters": {}, "semantic_query": query}

            # Parse JSON with fallback
            try:
                analysis = json.loads(content)
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(
                    "QueryAnalyzer: failed to parse LLM response as JSON: %s. "
                    "Raw content (first 500 chars): %s",
                    e,
                    content[:500],
                )
                return {"filters": {}, "semantic_query": query}

            # Guard against non-dict responses (e.g. LLM returns "null" or a list)
            if not isinstance(analysis, dict):
                logger.warning(
                    "QueryAnalyzer: LLM returned non-dict JSON: type=%s, value=%s",
                    type(analysis).__name__,
                    str(analysis)[:200],
                )
                return {"filters": {}, "semantic_query": query}

            filters = analysis.get("filters", {})
            semantic_query = analysis.get("semantic_query", query)

            logger.info("QueryAnalyzer: filters=%s, semantic_query=%s", filters, semantic_query)

            # Track completion
            langfuse.update_current_generation(
                output={
                    "filters": filters,
                    "has_semantic": bool(semantic_query),
                },
                usage_details={
                    "input": result.get("usage", {}).get("prompt_tokens", 0),
                    "output": result.get("usage", {}).get("completion_tokens", 0),
                },
            )

            return {"filters": filters, "semantic_query": semantic_query}

        except httpx.HTTPStatusError as e:
            logger.error(
                "QueryAnalyzer HTTP error: %s %s, body=%s",
                e.response.status_code,
                e.response.reason_phrase,
                e.response.text[:300],
            )
            return {"filters": {}, "semantic_query": query}
        except Exception as e:
            logger.error("QueryAnalyzer error: %s", e, exc_info=True)
            return {"filters": {}, "semantic_query": query}

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
