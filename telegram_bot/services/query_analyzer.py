"""Query analyzer service using LLM to extract filters."""

import json
import logging
from typing import Any

import httpx


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
                    "max_tokens": 500,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # Parse JSON with fallback
            try:
                analysis = json.loads(content)
                filters = analysis.get("filters", {})
                semantic_query = analysis.get("semantic_query", query)

                logger.info(f"QueryAnalyzer: filters={filters}, semantic_query={semantic_query}")

                return {"filters": filters, "semantic_query": semantic_query}

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from QueryAnalyzer: {e}")
                logger.error(f"Raw content: {content}")
                # Fallback: no filters, use original query
                return {"filters": {}, "semantic_query": query}

        except Exception as e:
            logger.error(f"QueryAnalyzer error: {e}", exc_info=True)
            # Fallback: no filters, use original query
            return {"filters": {}, "semantic_query": query}

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
