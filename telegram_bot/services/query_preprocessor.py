"""Query preprocessing for RAG pipeline optimization.

HyDEGenerator uses OpenAI SDK via Langfuse drop-in for auto-tracing.
QueryPreprocessor is rule-based (no LLM calls).
"""

import logging
import re
from typing import Any

import openai
from langfuse.openai import AsyncOpenAI

from telegram_bot.integrations.prompt_manager import get_prompt


logger = logging.getLogger(__name__)

_SHORT_FINANCE_QUERY_EXPANSIONS: dict[str, str] = {
    "рассрочки": "какие варианты рассрочки при покупке квартиры",
    "рассрочка": "какие варианты рассрочки при покупке квартиры",
}


def expand_short_query(query: str, *, topic_hint: str | None = None) -> str:
    """Expand short intent queries using deterministic templates."""
    normalized = query.strip().lower()
    if not normalized:
        return query
    if topic_hint != "finance":
        return query
    if len(normalized.split()) > 2:
        return query
    return _SHORT_FINANCE_QUERY_EXPANSIONS.get(normalized, query)


class HyDEGenerator:
    """Hypothetical Document Embeddings (HyDE) generator.

    HyDE improves retrieval for short/vague queries by:
    1. Generating a hypothetical answer to the query
    2. Embedding the hypothetical answer instead of the query
    3. Searching with the answer embedding (better semantic match)

    Best for: Short queries (< 5 words) without domain-specific keywords.
    Not recommended for: Exact queries (IDs, corpus numbers), long queries.
    """

    HYDE_SYSTEM_PROMPT = """Ты - эксперт по недвижимости.
Твоя задача: написать короткий гипотетический ответ на вопрос пользователя,
как если бы ты описывал идеальный результат поиска.

ПРАВИЛА:
1. Пиши 2-3 предложения, описывающих типичный объект недвижимости
2. Включай релевантные детали: город, тип, цена, площадь, особенности
3. Пиши на русском языке
4. НЕ задавай уточняющих вопросов
5. НЕ пиши вступление типа "Вот пример..."

Пример вопроса: "квартира у моря"
Пример ответа: "Уютная двухкомнатная квартира в Несебре, 50м², в 200 метрах от пляжа. Полностью меблирована, с балконом и видом на море. Цена 65,000 евро, поддержка 8 евро/м² в год."
"""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = "http://localhost:4000",
        model: str = "gpt-4o-mini",
    ):
        self.api_key = api_key or "not-needed"
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            max_retries=2,
            timeout=30.0,
        )

    async def generate_hypothetical_document(self, query: str) -> str:
        """Generate a hypothetical document that would answer the query.

        Args:
            query: User query (typically short, < 5 words)

        Returns:
            Hypothetical document text for embedding
        """
        try:
            system_prompt = get_prompt("hyde", fallback=self.HYDE_SYSTEM_PROMPT)
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=0.7,
                max_tokens=200,
                name="hyde-generate",  # type: ignore[call-overload]  # langfuse kwarg
            )

            hypothetical_doc = response.choices[0].message.content or query
            logger.info("HyDE generated doc for '%s': %s...", query, hypothetical_doc[:100])
            return hypothetical_doc

        except (
            openai.APIConnectionError,
            openai.RateLimitError,
            openai.APITimeoutError,
        ) as e:
            logger.error("HyDE generation API error: %s", e)
            return query
        except Exception as e:
            logger.error("HyDE generation failed: %s", e)
            return query

    async def close(self):
        """Close the OpenAI client."""
        await self.client.close()


class QueryPreprocessor:
    """Preprocesses queries for optimal search and caching.

    Handles:
    - Transliteration normalization (Latin -> Cyrillic place names)
    - Dynamic RRF weight calculation based on query type
    - Adaptive cache threshold selection

    Note: This is separate from QueryAnalyzer which uses LLM for filter extraction.
    QueryPreprocessor is rule-based and runs before QueryAnalyzer.
    """

    # Transliteration map: Latin -> Cyrillic (Bulgarian cities and resorts)
    TRANSLIT_MAP = {
        # Cities
        "Burgas": "Бургас",
        "Varna": "Варна",
        "Sofia": "София",
        "Plovdiv": "Пловдив",
        # Resorts
        "Nesebar": "Несебър",
        "Nessebar": "Несебър",
        "Sozopol": "Созопол",
        "Pomorie": "Поморие",
        "Sunny Beach": "Солнечный берег",
        "Sveti Vlas": "Святой Влас",
        "Svyati Vlas": "Святой Влас",
        "St Vlas": "Святой Влас",
        "Elenite": "Елените",
        "Ravda": "Равда",
        "Sarafovo": "Сарафово",
        "Primorsko": "Приморско",
        "Tsarevo": "Царево",
        "Lozenets": "Лозенец",
        "Golden Sands": "Золотые пески",
        "Albena": "Албена",
        "Balchik": "Балчик",
        "Kavarna": "Каварна",
        "Obzor": "Обзор",
        "Byala": "Бяла",
    }

    # Patterns indicating exact search (favor sparse vectors)
    EXACT_PATTERNS = [
        r"\bID\s*\d+",  # "ID 12345"
        r"\b\d{5,}\b",  # Long numbers (IDs)
        r"корпус\s*\d+",  # "корпус 5"
        r"корпус\s*[А-Яа-яA-Za-z]",  # corpus with letter (e.g. A)
        r"блок\s*\d+",  # "блок 3"
        r"блок\s*[А-Яа-яA-Za-z]",  # block with letter (e.g. B)
        r"секция\s*\d+",  # "секция 2"
        r"этаж\s*\d+",  # "этаж 5"
        r"ЖК\s+\w+",  # "ЖК Елените"
    ]

    # Patterns requiring strict cache threshold
    STRICT_CACHE_PATTERNS = [
        r"\b\d{3,}\b",  # Numbers 3+ digits
        r"корпус",
        r"блок",
        r"секция",
        r"этаж",
        r"\bID\b",
    ]

    def normalize_translit(self, query: str) -> str:
        """Convert Latin place names to Cyrillic for BM42 sparse search."""
        normalized = query

        for latin, cyrillic in self.TRANSLIT_MAP.items():
            pattern = re.compile(re.escape(latin), re.IGNORECASE)
            normalized = pattern.sub(cyrillic, normalized)

        if normalized != query:
            logger.debug("Translit normalized: '%s' -> '%s'", query, normalized)

        return normalized

    def get_rrf_weights(self, query: str) -> tuple[float, float]:
        """Calculate RRF fusion weights based on query type."""
        for pattern in self.EXACT_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.debug("Exact query detected, using sparse-favored weights")
                return (0.2, 0.8)

        return (0.6, 0.4)

    def get_cache_threshold(self, query: str) -> float:
        """Get cache similarity threshold based on query type."""
        for pattern in self.STRICT_CACHE_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.debug("Strict cache threshold for query with identifiers")
                return 0.05

        return 0.10

    def has_exact_identifier(self, query: str) -> bool:
        """Check if query contains exact identifiers."""
        return any(re.search(pattern, query, re.IGNORECASE) for pattern in self.EXACT_PATTERNS)

    def count_words(self, query: str) -> int:
        """Count words in query (for HyDE threshold)."""
        return len(query.split())

    def should_use_hyde(self, query: str, min_words: int = 5) -> bool:
        """Determine if HyDE should be applied to this query."""
        if self.has_exact_identifier(query):
            logger.debug("HyDE skipped: query has exact identifiers")
            return False

        word_count = self.count_words(query)
        should_hyde = word_count < min_words

        if should_hyde:
            logger.debug("HyDE enabled: short query (%d words < %d)", word_count, min_words)
        else:
            logger.debug("HyDE skipped: long query (%d words >= %d)", word_count, min_words)

        return should_hyde

    def analyze(
        self, query: str, use_hyde: bool = False, hyde_min_words: int = 5
    ) -> dict[str, Any]:
        """Perform full query preprocessing analysis."""
        normalized = self.normalize_translit(query)
        dense_w, sparse_w = self.get_rrf_weights(query)
        is_exact = self.has_exact_identifier(query)
        word_count = self.count_words(query)

        apply_hyde = use_hyde and self.should_use_hyde(query, hyde_min_words)

        return {
            "original_query": query,
            "normalized_query": normalized,
            "rrf_weights": {"dense": dense_w, "sparse": sparse_w},
            "cache_threshold": self.get_cache_threshold(query),
            "is_exact": is_exact,
            "use_hyde": apply_hyde,
            "word_count": word_count,
        }
