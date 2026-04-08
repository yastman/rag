"""Unit tests for src/retrieval/search_engines.py."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from qdrant_client import models

from src.config import AcornMode, QuantizationMode, SearchEngine, Settings
from src.retrieval.search_engine_shared import lexical_weights_to_sparse as shared_sparse
from src.retrieval.search_engines import (
    BaselineSearchEngine,
    HybridRRFSearchEngine,
    SearchResult,
    create_search_engine,
    lexical_weights_to_sparse,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_settings() -> Settings:
    s = MagicMock(spec=Settings)
    s.qdrant_url = "http://localhost:6333"
    s.acorn_mode = AcornMode.OFF
    s.quantization_mode = QuantizationMode.OFF
    s.quantization_rescore = True
    s.quantization_oversampling = 2.0
    s.acorn_enabled_selectivity_threshold = 0.5
    s.acorn_max_selectivity = 1.0
    s.search_engine = SearchEngine.BASELINE
    s.get_collection_name.return_value = "test_collection"
    return s


@pytest.fixture
def baseline_engine(mock_settings: Settings) -> BaselineSearchEngine:
    with patch("src.retrieval.search_engines.QdrantClient"):
        engine = BaselineSearchEngine(mock_settings)
        engine.client = MagicMock()
    return engine


# ---------------------------------------------------------------------------
# lexical_weights_to_sparse
# ---------------------------------------------------------------------------


class TestLexicalWeightsToSparse:
    def test_retrieval_module_reexports_shared_helper(self) -> None:
        assert lexical_weights_to_sparse is shared_sparse

    def test_empty_dict_returns_empty_sparse(self) -> None:
        result = lexical_weights_to_sparse({})
        assert result.indices == []
        assert result.values == []

    def test_converts_string_keys_to_int_indices(self) -> None:
        result = lexical_weights_to_sparse({"10": 0.5, "20": 0.3})
        assert 10 in result.indices
        assert 20 in result.indices

    def test_preserves_values(self) -> None:
        weights = {"5": 0.9}
        result = lexical_weights_to_sparse(weights)
        assert 0.9 in result.values


# ---------------------------------------------------------------------------
# _should_use_acorn
# ---------------------------------------------------------------------------


class TestShouldUseAcorn:
    def test_acorn_off_returns_false_with_filters(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        baseline_engine.settings.acorn_mode = AcornMode.OFF
        assert (
            baseline_engine._should_use_acorn(has_filters=True, estimated_selectivity=0.1) is False
        )

    def test_acorn_off_returns_false_without_filters(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        baseline_engine.settings.acorn_mode = AcornMode.OFF
        assert (
            baseline_engine._should_use_acorn(has_filters=False, estimated_selectivity=None)
            is False
        )

    def test_acorn_on_with_filters_returns_true(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        baseline_engine.settings.acorn_mode = AcornMode.ON
        assert (
            baseline_engine._should_use_acorn(has_filters=True, estimated_selectivity=0.8) is True
        )

    def test_acorn_on_without_filters_returns_false(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        baseline_engine.settings.acorn_mode = AcornMode.ON
        assert (
            baseline_engine._should_use_acorn(has_filters=False, estimated_selectivity=None)
            is False
        )

    def test_acorn_auto_no_filters_returns_false(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        baseline_engine.settings.acorn_mode = AcornMode.AUTO
        assert (
            baseline_engine._should_use_acorn(has_filters=False, estimated_selectivity=0.1) is False
        )

    def test_acorn_auto_unknown_selectivity_returns_true(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        baseline_engine.settings.acorn_mode = AcornMode.AUTO
        assert (
            baseline_engine._should_use_acorn(has_filters=True, estimated_selectivity=None) is True
        )

    def test_acorn_auto_low_selectivity_returns_true(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        baseline_engine.settings.acorn_mode = AcornMode.AUTO
        baseline_engine.settings.acorn_enabled_selectivity_threshold = 0.5
        assert (
            baseline_engine._should_use_acorn(has_filters=True, estimated_selectivity=0.1) is True
        )

    def test_acorn_auto_high_selectivity_returns_false(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        baseline_engine.settings.acorn_mode = AcornMode.AUTO
        baseline_engine.settings.acorn_enabled_selectivity_threshold = 0.5
        assert (
            baseline_engine._should_use_acorn(has_filters=True, estimated_selectivity=0.9) is False
        )


# ---------------------------------------------------------------------------
# _build_search_params
# ---------------------------------------------------------------------------


class TestBuildSearchParams:
    def test_returns_search_params_instance(self, baseline_engine: BaselineSearchEngine) -> None:
        params = baseline_engine._build_search_params()
        assert isinstance(params, models.SearchParams)

    def test_quantization_ignore_true_when_off(self, baseline_engine: BaselineSearchEngine) -> None:
        baseline_engine.settings.quantization_mode = QuantizationMode.OFF
        params = baseline_engine._build_search_params()
        assert params.quantization is not None
        assert params.quantization.ignore is True

    def test_quantization_ignore_false_when_not_off(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        baseline_engine.settings.quantization_mode = QuantizationMode.SCALAR
        params = baseline_engine._build_search_params()
        assert params.quantization is not None
        assert params.quantization.ignore is False

    def test_no_acorn_when_acorn_mode_off(self, baseline_engine: BaselineSearchEngine) -> None:
        baseline_engine.settings.acorn_mode = AcornMode.OFF
        params = baseline_engine._build_search_params(has_filters=True)
        # acorn attribute should not be set or should be None
        assert not hasattr(params, "acorn") or params.acorn is None


# ---------------------------------------------------------------------------
# _parse_group_results
# ---------------------------------------------------------------------------


class TestParseGroupResults:
    def _make_group_response(self, groups_data: list[list[dict]]) -> MagicMock:
        """Build a mock grouped response."""
        response = MagicMock()
        response.groups = []
        for hits_data in groups_data:
            group = MagicMock()
            hits = []
            for d in hits_data:
                point = MagicMock()
                point.score = d["score"]
                point.payload = {
                    "page_content": d.get("text", ""),
                    "metadata": {"article_number": d.get("article_number", "")},
                }
                hits.append(point)
            group.hits = hits
            response.groups.append(group)
        return response

    def test_empty_groups(self, baseline_engine: BaselineSearchEngine) -> None:
        response = self._make_group_response([])
        results = baseline_engine._parse_group_results(response)
        assert results == []

    def test_single_group_single_hit(self, baseline_engine: BaselineSearchEngine) -> None:
        response = self._make_group_response(
            [[{"score": 0.9, "text": "hello", "article_number": "A1"}]]
        )
        results = baseline_engine._parse_group_results(response)
        assert len(results) == 1
        assert results[0].score == 0.9
        assert results[0].text == "hello"
        assert results[0].article_number == "A1"

    def test_multiple_groups(self, baseline_engine: BaselineSearchEngine) -> None:
        response = self._make_group_response(
            [
                [{"score": 0.9, "text": "doc1", "article_number": "A1"}],
                [{"score": 0.7, "text": "doc2", "article_number": "A2"}],
            ]
        )
        results = baseline_engine._parse_group_results(response)
        assert len(results) == 2

    def test_preserves_order(self, baseline_engine: BaselineSearchEngine) -> None:
        response = self._make_group_response(
            [
                [{"score": 0.9, "article_number": "FIRST"}],
                [{"score": 0.5, "article_number": "SECOND"}],
            ]
        )
        results = baseline_engine._parse_group_results(response)
        assert results[0].article_number == "FIRST"
        assert results[1].article_number == "SECOND"


# ---------------------------------------------------------------------------
# BaselineSearchEngine.search
# ---------------------------------------------------------------------------


class TestBaselineEngineSearch:
    def _make_response(self, points_data: list[dict]) -> MagicMock:
        response = MagicMock()
        points = []
        for d in points_data:
            p = MagicMock()
            p.score = d["score"]
            p.payload = {
                "page_content": d.get("text", ""),
                "metadata": {"article_number": d.get("article_number", "")},
            }
            points.append(p)
        response.points = points
        return response

    def test_raises_type_error_for_string_input(
        self, baseline_engine: BaselineSearchEngine
    ) -> None:
        with pytest.raises(TypeError, match="requires pre-computed embeddings"):
            baseline_engine.search("some query string")

    def test_returns_search_results(self, baseline_engine: BaselineSearchEngine) -> None:
        baseline_engine.client.query_points.return_value = self._make_response(
            [
                {"score": 0.8, "text": "result text", "article_number": "X1"},
            ]
        )
        results = baseline_engine.search([0.1, 0.2, 0.3])
        assert len(results) == 1
        assert isinstance(results[0], SearchResult)
        assert results[0].score == 0.8

    def test_default_score_threshold_05(self, baseline_engine: BaselineSearchEngine) -> None:
        baseline_engine.client.query_points.return_value = self._make_response([])
        baseline_engine.search([0.1, 0.2])
        call_kwargs = baseline_engine.client.query_points.call_args[1]
        assert call_kwargs["score_threshold"] == 0.5

    def test_custom_score_threshold_used(self, baseline_engine: BaselineSearchEngine) -> None:
        baseline_engine.client.query_points.return_value = self._make_response([])
        baseline_engine.search([0.1, 0.2], score_threshold=0.7)
        call_kwargs = baseline_engine.client.query_points.call_args[1]
        assert call_kwargs["score_threshold"] == 0.7

    def test_empty_results(self, baseline_engine: BaselineSearchEngine) -> None:
        baseline_engine.client.query_points.return_value = self._make_response([])
        results = baseline_engine.search([0.1, 0.2])
        assert results == []


# ---------------------------------------------------------------------------
# HybridRRFSearchEngine
# ---------------------------------------------------------------------------


class TestHybridRRFEngineSearch:
    @pytest.fixture
    def hybrid_engine(self, mock_settings: Settings) -> HybridRRFSearchEngine:
        with (
            patch("src.retrieval.search_engines.QdrantClient"),
            patch("src.retrieval.search_engines.get_bge_m3_model"),
        ):
            engine = HybridRRFSearchEngine(mock_settings)
            engine.client = MagicMock()
        return engine

    def test_default_score_threshold_03(self, hybrid_engine: HybridRRFSearchEngine) -> None:
        response = MagicMock()
        response.points = []
        hybrid_engine.client.query_points.return_value = response

        hybrid_engine.search([0.1, 0.2], score_threshold=None)
        call_kwargs = hybrid_engine.client.query_points.call_args[1]
        assert call_kwargs["score_threshold"] == 0.3

    def test_dense_vector_search_when_list_provided(
        self, hybrid_engine: HybridRRFSearchEngine
    ) -> None:
        response = MagicMock()
        response.points = []
        hybrid_engine.client.query_points.return_value = response

        hybrid_engine.search([0.1, 0.2, 0.3])
        call_kwargs = hybrid_engine.client.query_points.call_args[1]
        assert call_kwargs["using"] == "dense"


# ---------------------------------------------------------------------------
# Engine names
# ---------------------------------------------------------------------------


class TestEngineNames:
    def test_baseline_engine_name(self, mock_settings: Settings) -> None:
        with patch("src.retrieval.search_engines.QdrantClient"):
            engine = BaselineSearchEngine(mock_settings)
        assert engine.get_name() == "baseline"

    def test_hybrid_rrf_engine_name(self, mock_settings: Settings) -> None:
        with (
            patch("src.retrieval.search_engines.QdrantClient"),
            patch("src.retrieval.search_engines.get_bge_m3_model"),
        ):
            engine = HybridRRFSearchEngine(mock_settings)
        assert engine.get_name() == "hybrid_rrf"


# ---------------------------------------------------------------------------
# create_search_engine factory
# ---------------------------------------------------------------------------


class TestCreateSearchEngine:
    def test_creates_baseline_for_baseline_engine_type(self, mock_settings: Settings) -> None:
        with patch("src.retrieval.search_engines.QdrantClient"):
            engine = create_search_engine(SearchEngine.BASELINE, settings=mock_settings)
        assert isinstance(engine, BaselineSearchEngine)

    def test_creates_hybrid_rrf_for_hybrid_engine_type(self, mock_settings: Settings) -> None:
        with (
            patch("src.retrieval.search_engines.QdrantClient"),
            patch("src.retrieval.search_engines.get_bge_m3_model"),
        ):
            engine = create_search_engine(SearchEngine.HYBRID_RRF, settings=mock_settings)
        assert isinstance(engine, HybridRRFSearchEngine)

    def test_uses_settings_engine_type_when_none(self, mock_settings: Settings) -> None:
        mock_settings.search_engine = SearchEngine.BASELINE
        with patch("src.retrieval.search_engines.QdrantClient"):
            engine = create_search_engine(None, settings=mock_settings)
        assert isinstance(engine, BaselineSearchEngine)

    def test_returns_search_engine_instance(self, mock_settings: Settings) -> None:
        with patch("src.retrieval.search_engines.QdrantClient"):
            engine = create_search_engine(SearchEngine.BASELINE, settings=mock_settings)
        assert engine is not None
        assert hasattr(engine, "search")
        assert hasattr(engine, "get_name")

    def test_unknown_engine_type_falls_back_to_best_engine(self, mock_settings: Settings) -> None:
        with (
            patch("src.retrieval.search_engines.QdrantClient"),
            patch("src.retrieval.search_engines.get_bge_m3_model"),
        ):
            engine = create_search_engine("unknown", settings=mock_settings)  # type: ignore[arg-type]
        from src.retrieval.search_engines import HybridRRFColBERTSearchEngine

        assert isinstance(engine, HybridRRFColBERTSearchEngine)
