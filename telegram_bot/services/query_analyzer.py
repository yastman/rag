"""Query analyzer service using LiteLLM JSON-schema structured output."""

import logging
from typing import Any

import openai
from pydantic import BaseModel, Field

from src.runtime.integrations.prompt_manager import get_prompt_with_object
from src.runtime.llm import create_litellm_chat_client


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
- furnished (bool): true (если упомянута мебель), false (если явно указано "без мебели")
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
    """Pydantic model for query analysis extraction via JSON-schema output."""

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
        self.client = create_litellm_chat_client(model=model, timeout=30.0)
        self._structured_client = self.client

    async def analyze(self, query: str) -> dict[str, Any]:
        """Analyze query and extract filters + semantic query.

        Args:
            query: User query text

        Returns:
            Dict with 'filters' and 'semantic_query'
        """
        try:
            system_prompt, _prompt_obj = get_prompt_with_object(
                "query-analysis", fallback=SYSTEM_PROMPT
            )
            create_kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Запрос пользователя: {query}"},
                ],
                "response_model": QueryAnalysisResult,
                "max_retries": 2,
                "temperature": 0.0,
                "max_tokens": 1000,
            }
            result = await self._structured_client.chat.completions.create(**create_kwargs)

            filters = result.filters
            semantic_query = result.semantic_query or query

            logger.info("QueryAnalyzer: filters=%s, semantic_query=%s", filters, semantic_query)
            return {"filters": filters, "semantic_query": semantic_query}

        except (openai.APIConnectionError, openai.RateLimitError, openai.APITimeoutError) as e:
            logger.error("QueryAnalyzer API error: %s", e)
            return {"filters": {}, "semantic_query": query}
        except Exception as e:
            logger.error("QueryAnalyzer error: %s", e, exc_info=True)
            return {"filters": {}, "semantic_query": query}

    async def close(self):
        """Close the underlying client when it exposes an async close hook."""
        close = getattr(self.client, "close", None)
        if close is not None:
            await close()
