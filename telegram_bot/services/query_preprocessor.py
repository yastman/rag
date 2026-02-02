"""Query preprocessing for RAG pipeline optimization."""

import logging
import re
from typing import Any

from langfuse import observe


logger = logging.getLogger(__name__)


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

    @observe(name="query-preprocessor-analyze")
    def analyze(self, query: str) -> dict[str, Any]:
        """Perform full query preprocessing analysis.

        Args:
            query: User query.

        Returns:
            Dict containing:
            - original_query: Original input
            - normalized_query: After translit normalization
            - rrf_weights: {"dense": float, "sparse": float}
            - cache_threshold: float
            - is_exact: bool
        """
        normalized = self.normalize_translit(query)
        dense_w, sparse_w = self.get_rrf_weights(query)

        return {
            "original_query": query,
            "normalized_query": normalized,
            "rrf_weights": {"dense": dense_w, "sparse": sparse_w},
            "cache_threshold": self.get_cache_threshold(query),
            "is_exact": self.has_exact_identifier(query),
        }
