"""Unit tests for shared search engine helpers."""

import numpy as np
import pytest

from src.retrieval.search_engine_shared import (
    AbstractSearchEngine,
    create_engine_from_registry,
    lexical_weights_to_sparse,
)


class FakeSparse:
    indices = np.array([10])
    values = np.array([0.5])

    def __bool__(self) -> bool:
        raise TypeError("truthiness should not be evaluated")


def test_abstract_search_engine_stays_abstract() -> None:
    with pytest.raises(TypeError):
        AbstractSearchEngine()


def test_sparse_helper_accepts_dict_and_scipy_like_values() -> None:
    dict_sparse = lexical_weights_to_sparse({"10": 0.5, "20": 0.3})
    scipy_sparse = lexical_weights_to_sparse(FakeSparse())
    empty_sparse = lexical_weights_to_sparse(None)

    assert dict_sparse.indices == [10, 20]
    assert dict_sparse.values == [0.5, 0.3]
    assert scipy_sparse.indices == [10]
    assert scipy_sparse.values == pytest.approx([0.5])
    assert empty_sparse.indices == []
    assert empty_sparse.values == []


def test_factory_uses_default_or_raises_based_on_flags() -> None:
    registry = {"baseline": lambda: "baseline", "best": lambda: "best"}

    assert (
        create_engine_from_registry(
            None,
            registry=registry,
            default_key="best",
            fallback_on_unknown=True,
        )
        == "best"
    )

    with pytest.raises(ValueError, match="Unknown engine type: unknown"):
        create_engine_from_registry(
            "unknown",
            registry=registry,
            default_key="best",
            fallback_on_unknown=False,
        )
