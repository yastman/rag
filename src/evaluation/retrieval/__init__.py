"""Evaluation retrieval package.

This package contains evaluation-only search engines and helpers for benchmarking.

The modules in this package re-export implementations from the production retrieval
package to provide a canonical namespace for evaluation while keeping the evaluation
code separate from runtime services.
"""

from .search_engine_shared import (
    AbstractSearchEngine,
    create_engine_from_registry,
)
from .search_engines import (
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
    "AbstractSearchEngine",
    "BaseSearchEngine",
    "BaselineSearchEngine",
    "DBSFColBERTSearchEngine",
    "HybridRRFColBERTSearchEngine",
    "HybridRRFSearchEngine",
    "SearchEngine",
    "SearchResult",
    "create_engine_from_registry",
    "create_search_engine",
    "lexical_weights_to_sparse",
]
