"""Parity pins for the two live query helpers (#3429).

``expand_short_query`` backs deterministic short-query expansion in the rewrite
stage and ``get_rrf_weights`` supplies the dense/sparse fusion weights used by
hybrid retrieval. #3429 deleted the dormant HyDE / query-analysis surface that
used to surround them; these tests pin the exact outputs of the retained
helpers so the deletion cannot change retrieval behavior.
"""

from __future__ import annotations

import pytest

from src.runtime.pipeline._retrieve import _compute_retrieval_filters
from src.runtime.services.query_preprocessor import expand_short_query


_FINANCE_EXPANSION = "какие варианты рассрочки при покупке квартиры"

# Exact-versus-semantic behavior table shared by the direct helper test and the
# retrieval-filter-owner test. Every EXACT pattern family has one row.
_RRF_TABLE = [
    pytest.param("квартиры у моря недорого", 0.6, 0.4, id="semantic"),
    pytest.param("квартира 1234", 0.6, 0.4, id="four_digits_stay_semantic"),
    pytest.param("показать ID 12345", 0.2, 0.8, id="id"),
    pytest.param("id 777", 0.2, 0.8, id="id_lowercase"),
    pytest.param("объект 123456", 0.2, 0.8, id="long_number"),
    pytest.param("квартира корпус 5", 0.2, 0.8, id="corpus_number"),
    pytest.param("корпус A", 0.2, 0.8, id="corpus_letter"),
    pytest.param("блок 3 этаж 2", 0.2, 0.8, id="block_number"),
    pytest.param("блок B", 0.2, 0.8, id="block_letter"),
    pytest.param("секция 2", 0.2, 0.8, id="section"),
    pytest.param("этаж 5 вид на море", 0.2, 0.8, id="floor"),
    pytest.param("ЖК Елените апартаменты", 0.2, 0.8, id="zhk"),
]


class TestExpandShortQueryParity:
    """Exact outputs of the deterministic expansion used by the rewrite stage."""

    @pytest.mark.parametrize("query", ["рассрочки", "рассрочка"])
    def test_finance_keys_expand_to_exact_template(self, query: str) -> None:
        assert expand_short_query(query, topic_hint="finance") == _FINANCE_EXPANSION

    def test_key_lookup_normalizes_case_and_whitespace(self) -> None:
        assert expand_short_query("  Рассрочки ", topic_hint="finance") == _FINANCE_EXPANSION

    @pytest.mark.parametrize("topic_hint", [None, "legal", "relocation"])
    def test_non_finance_topic_returns_query_unchanged(self, topic_hint: str | None) -> None:
        assert expand_short_query("рассрочки", topic_hint=topic_hint) == "рассрочки"

    @pytest.mark.parametrize("query", ["", "   "])
    def test_blank_query_returns_original_object_unchanged(self, query: str) -> None:
        assert expand_short_query(query, topic_hint="finance") == query

    def test_more_than_two_words_is_never_expanded(self) -> None:
        query = "варианты рассрочки квартиры"
        assert expand_short_query(query, topic_hint="finance") == query

    @pytest.mark.parametrize("query", ["рассрочки вопрос", "ВНЖ"])
    def test_short_finance_query_without_key_is_unchanged(self, query: str) -> None:
        assert expand_short_query(query, topic_hint="finance") == query


class TestRrfWeightsThroughRetrievalFilterOwner:
    """Weights observed on the production plan built by ``_compute_retrieval_filters``."""

    @pytest.mark.parametrize(("query", "dense", "sparse"), _RRF_TABLE)
    def test_plan_weights_follow_exact_vs_semantic_table(
        self, query: str, dense: float, sparse: float
    ) -> None:
        plan = _compute_retrieval_filters(query, None, None)
        assert (plan.dense_weight, plan.sparse_weight) == (dense, sparse)

    def test_weights_depend_on_query_text_not_topic_or_filters(self) -> None:
        semantic = _compute_retrieval_filters("ВНЖ", {"city": "X"}, "finance")
        exact = _compute_retrieval_filters("ID 12345", {"city": "X"}, "finance")
        assert (semantic.dense_weight, semantic.sparse_weight) == (0.6, 0.4)
        assert (exact.dense_weight, exact.sparse_weight) == (0.2, 0.8)


class TestGetRrfWeightsHelper:
    """Direct pins on the module-level helper that owns the weighting rule."""

    @pytest.mark.parametrize(("query", "dense", "sparse"), _RRF_TABLE)
    def test_helper_matches_behavior_table(self, query: str, dense: float, sparse: float) -> None:
        from src.runtime.services.query_preprocessor import get_rrf_weights

        assert get_rrf_weights(query) == (dense, sparse)

    @pytest.mark.parametrize("query", ["semantic query", "ID 12345", "корпус 5", "блок А этаж 3"])
    def test_weights_sum_to_one(self, query: str) -> None:
        from src.runtime.services.query_preprocessor import get_rrf_weights

        dense, sparse = get_rrf_weights(query)
        assert dense + sparse == pytest.approx(1.0)
