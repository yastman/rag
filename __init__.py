"""
Contextual RAG Pipeline - Next-Gen Implementation
Anthropic Contextual Retrieval + Lightweight Knowledge Graph
"""

__version__ = "1.0.0"

from .contextualize import ContextualRetrieval
from .utils.structure_parser import (
    add_graph_edges,
    extract_contextual_prefix,
    extract_related_articles,
    parse_legal_structure,
)


__all__ = [
    "ContextualRetrieval",
    "add_graph_edges",
    "extract_contextual_prefix",
    "extract_related_articles",
    "parse_legal_structure",
]
