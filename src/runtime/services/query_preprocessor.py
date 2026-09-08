"""Live query helpers for the retrieval pipeline.

Two rule-based helpers, no LLM calls:

- ``expand_short_query`` — deterministic expansion of short finance intents,
  used by the rewrite stage before any LLM rewrite is attempted.
- ``get_rrf_weights`` — dense/sparse RRF fusion weights derived from the query
  text, used by the hybrid retrieval filter plan.

#3429 deleted the dormant HyDE generator and query-analysis surface that used
to live alongside these helpers; their outputs are unchanged.
"""

import logging
import re

from src.runtime.domain_defaults import (
    SHORT_FINANCE_QUERY_EXPANSIONS as _DOMAIN_SHORT_FINANCE,
)


logger = logging.getLogger(__name__)


_SHORT_FINANCE_QUERY_EXPANSIONS: dict[str, str] = _DOMAIN_SHORT_FINANCE

# Patterns indicating exact search (favor sparse vectors)
EXACT_PATTERNS: tuple[str, ...] = (
    r"\bID\s*\d+",  # "ID 12345"
    r"\b\d{5,}\b",  # Long numbers (IDs)
    r"корпус\s*\d+",  # "корпус 5"
    r"корпус\s*[А-Яа-яA-Za-z]",  # corpus with letter (e.g. A)
    r"блок\s*\d+",  # "блок 3"
    r"блок\s*[А-Яа-яA-Za-z]",  # block with letter (e.g. B)
    r"секция\s*\d+",  # "секция 2"
    r"этаж\s*\d+",  # "этаж 5"
    r"ЖК\s+\w+",  # "ЖК Елените"
)


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


def get_rrf_weights(query: str) -> tuple[float, float]:
    """Calculate RRF fusion weights based on query type."""
    for pattern in EXACT_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            logger.debug("Exact query detected, using sparse-favored weights")
            return (0.2, 0.8)

    return (0.6, 0.4)
