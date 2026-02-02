"""Query preprocessing for RAG pipeline optimization."""

import logging
import re
from typing import Any

import httpx
from langfuse import get_client, observe


logger = logging.getLogger(__name__)


class HyDEGenerator:
    """Hypothetical Document Embeddings (HyDE) generator.

    HyDE improves retrieval for short/vague queries by:
    1. Generating a hypothetical answer to the query
    2. Embedding the hypothetical answer instead of the query
    3. Searching with the answer embedding (better semantic match)

    Best for: Short queries (< 5 words) without domain-specific keywords.
    Not recommended for: Exact queries (IDs, corpus numbers), long queries.
    """

    # System prompt for generating hypothetical documents
    HYDE_SYSTEM_PROMPT = """Ты - эксперт по недвижимости в Болгарии.
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
        client: httpx.AsyncClient | None = None,
    ):
        """Initialize HyDE generator.

        Args:
            api_key: API key for LLM service (optional, uses env if not set)
            base_url: LiteLLM proxy URL
            model: Model name to use
            client: Optional httpx client for dependency injection
        """
        self.api_key = api_key or "not-needed"  # LiteLLM proxy may not need key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=30.0)

    @observe(name="hyde-generate", as_type="generation")
    async def generate_hypothetical_document(self, query: str) -> str:
        """Generate a hypothetical document that would answer the query.

        Args:
            query: User query (typically short, < 5 words)

        Returns:
            Hypothetical document text for embedding
        """
        langfuse = get_client()

        # Track generation start
        langfuse.update_current_generation(
            input={"query": query},
            model=self.model,
        )

        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": self.HYDE_SYSTEM_PROMPT},
                        {"role": "user", "content": query},
                    ],
                    "temperature": 0.7,  # Some creativity for diverse results
                    "max_tokens": 200,  # Short hypothetical doc
                },
            )
            response.raise_for_status()

            data = response.json()
            hypothetical_doc: str = data["choices"][0]["message"]["content"]

            # Track completion
            langfuse.update_current_generation(
                output={"hypothetical_doc_length": len(hypothetical_doc)},
                usage_details={
                    "input": data.get("usage", {}).get("prompt_tokens", 0),
                    "output": data.get("usage", {}).get("completion_tokens", 0),
                },
            )

            logger.info(f"HyDE generated doc for '{query}': {hypothetical_doc[:100]}...")
            return hypothetical_doc

        except Exception as e:
            logger.error(f"HyDE generation failed: {e}")
            # Fallback: return original query
            return query

    async def close(self):
        """Close HTTP client if owned."""
        if self._owns_client:
            await self.client.aclose()


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
        """Convert Latin place names to Cyrillic for BM42 sparse search.

        Args:
            query: User query (may contain Latin transliterations).

        Returns:
            Query with Latin place names converted to Cyrillic.
        """
        normalized = query

        for latin, cyrillic in self.TRANSLIT_MAP.items():
            # Case-insensitive replacement
            pattern = re.compile(re.escape(latin), re.IGNORECASE)
            normalized = pattern.sub(cyrillic, normalized)

        if normalized != query:
            logger.debug(f"Translit normalized: '{query}' -> '{normalized}'")

        return normalized

    def get_rrf_weights(self, query: str) -> tuple[float, float]:
        """Calculate RRF fusion weights based on query type.

        For exact queries (IDs, corpus numbers), favor sparse (keyword) search.
        For semantic queries, favor dense (embedding) search.

        Args:
            query: User query.

        Returns:
            Tuple of (dense_weight, sparse_weight) summing to 1.0.
        """
        for pattern in self.EXACT_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.debug("Exact query detected, using sparse-favored weights")
                return (0.2, 0.8)  # Favor sparse for exact matches

        return (0.6, 0.4)  # Default: favor dense for semantic queries

    def get_cache_threshold(self, query: str) -> float:
        """Get cache similarity threshold based on query type.

        Stricter threshold for queries with specific identifiers
        to avoid false positive cache hits.

        Args:
            query: User query.

        Returns:
            Distance threshold (lower = stricter matching required).
        """
        for pattern in self.STRICT_CACHE_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                logger.debug("Strict cache threshold for query with identifiers")
                return 0.05  # 95% similarity required

        return 0.10  # Default 90% similarity

    def has_exact_identifier(self, query: str) -> bool:
        """Check if query contains exact identifiers.

        Args:
            query: User query.

        Returns:
            True if query contains IDs, corpus numbers, etc.
        """
        return any(re.search(pattern, query, re.IGNORECASE) for pattern in self.EXACT_PATTERNS)

    def count_words(self, query: str) -> int:
        """Count words in query (for HyDE threshold).

        Args:
            query: User query.

        Returns:
            Number of words (split by whitespace).
        """
        return len(query.split())

    def should_use_hyde(self, query: str, min_words: int = 5) -> bool:
        """Determine if HyDE should be applied to this query.

        HyDE is beneficial for:
        - Short queries (< min_words)
        - Queries without exact identifiers (IDs, corpus numbers)
        - Semantic/conceptual queries

        HyDE is NOT beneficial for:
        - Long, detailed queries (already have good context)
        - Exact queries with IDs, corpus numbers
        - Queries that already match document vocabulary

        Args:
            query: User query.
            min_words: Minimum word count threshold (queries with fewer words use HyDE).

        Returns:
            True if HyDE should be applied.
        """
        # Don't use HyDE for exact identifier queries
        if self.has_exact_identifier(query):
            logger.debug("HyDE skipped: query has exact identifiers")
            return False

        # Use HyDE for short queries (< min_words)
        word_count = self.count_words(query)
        should_hyde = word_count < min_words

        if should_hyde:
            logger.debug(f"HyDE enabled: short query ({word_count} words < {min_words})")
        else:
            logger.debug(f"HyDE skipped: long query ({word_count} words >= {min_words})")

        return should_hyde

    @observe(name="query-preprocessor-analyze")
    def analyze(self, query: str, use_hyde: bool = False, hyde_min_words: int = 5) -> dict[str, Any]:
        """Perform full query preprocessing analysis.

        Args:
            query: User query.
            use_hyde: Whether HyDE feature is enabled globally.
            hyde_min_words: Minimum words threshold for HyDE.

        Returns:
            Dict containing:
            - original_query: Original input
            - normalized_query: After translit normalization
            - rrf_weights: {"dense": float, "sparse": float}
            - cache_threshold: float
            - is_exact: bool
            - use_hyde: bool (whether HyDE should be applied)
            - word_count: int
        """
        normalized = self.normalize_translit(query)
        dense_w, sparse_w = self.get_rrf_weights(query)
        is_exact = self.has_exact_identifier(query)
        word_count = self.count_words(query)

        # Determine if HyDE should be used for this specific query
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
