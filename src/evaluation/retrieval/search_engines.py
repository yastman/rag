"""Evaluation-only search engines for retrieval.

This module exposes evaluation search engines and helpers. It re-exports implementations
from ``src.retrieval.search_engines`` to maintain backwards compatibility.
"""

# Re-export evaluation search engines from the retrieval module
from src.retrieval.search_engines import (
    ACORN_AVAILABLE,
    BaselineSearchEngine,
    BaseSearchEngine,
    DBSFColBERTSearchEngine,
    HybridRRFColBERTSearchEngine,
    HybridRRFSearchEngine,
    SearchEngine,
    SearchResult,
    create_search_engine,
    lexical_weights_to_sparse,
)


__all__ = [
    "ACORN_AVAILABLE",
    "BaseSearchEngine",
    "BaselineSearchEngine",
    "DBSFColBERTSearchEngine",
    "HybridRRFColBERTSearchEngine",
    "HybridRRFSearchEngine",
    "SearchEngine",
    "SearchResult",
    "create_search_engine",
    "lexical_weights_to_sparse",
]
