"""Shared primitives for retrieval and evaluation search engines."""

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from typing import TypeVar

from qdrant_client import models


T = TypeVar("T")


class AbstractSearchEngine(ABC):
    """Minimal abstract contract shared by search engine wrappers."""

    @abstractmethod
    def search(self, *args, **kwargs):
        """Execute a search query."""
        raise NotImplementedError


def lexical_weights_to_sparse(lexical_weights) -> models.SparseVector:
    """Convert lexical weights into a Qdrant sparse vector."""
    if hasattr(lexical_weights, "indices") and hasattr(lexical_weights, "values"):
        return models.SparseVector(
            indices=lexical_weights.indices.tolist(),
            values=lexical_weights.values.tolist(),
        )
    if lexical_weights is None:
        return models.SparseVector(indices=[], values=[])
    if not lexical_weights:
        return models.SparseVector(indices=[], values=[])
    return models.SparseVector(
        indices=[int(k) for k in lexical_weights],
        values=list(lexical_weights.values()),
    )


def create_engine_from_registry(
    engine_key: str | None,
    *,
    registry: Mapping[str, Callable[[], T]],
    default_key: str | None = None,
    fallback_on_unknown: bool = False,
) -> T:
    """Resolve and instantiate a search engine from a small registry."""
    resolved_key = engine_key or default_key
    if resolved_key is not None and resolved_key in registry:
        return registry[resolved_key]()
    if fallback_on_unknown and default_key is not None:
        return registry[default_key]()
    raise ValueError(f"Unknown engine type: {engine_key}")
