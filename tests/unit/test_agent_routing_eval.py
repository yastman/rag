"""Unit tests for agent_routing_eval script (TDD: written before implementation).

Tests cover:
- Loading golden set from YAML
- Black-box evaluation (final answer vs expected)
- Trajectory evaluation (tool call sequence)
- Single-step evaluation (tool call parameters)
- Aggregated metrics
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest
import yaml


# ---------------------------------------------------------------------------
# Fixtures — minimal golden set and trajectory data
# ---------------------------------------------------------------------------

SAMPLE_GOLDEN_YAML = textwrap.dedent(
    """
    version: "1.0"
    description: Test golden set
    examples:
      - id: 1
        query: "Сколько стоит квартира в Балчике?"
        route: apartment_search
        expected_tools:
          - apartment_search
        tool_params:
          apartment_search:
            query: "квартира Балчик"
        answer_keywords:
          - "€"
          - "апартамент"

      - id: 2
        query: "Расскажи о процедуре покупки"
        route: rag_search
        expected_tools:
          - rag_search
        tool_params:
          rag_search:
            query: "процедура покупки"
        answer_keywords:
          - "договор"

      - id: 3
        query: "Привет!"
        route: direct
        expected_tools: []
        tool_params: {}
        answer_keywords:
          - "привет"

      - id: 4
        query: "Создай сделку для Ивана"
        route: crm_create_lead
        expected_tools:
          - crm_create_lead
        tool_params:
          crm_create_lead:
            name: "Иван"
        answer_keywords:
          - "создан"
    """
)


@pytest.fixture()
def golden_yaml_file(tmp_path: Path) -> Path:
    p = tmp_path / "golden.yaml"
    p.write_text(SAMPLE_GOLDEN_YAML)
    return p


@pytest.fixture()
def sample_examples() -> list[dict[str, Any]]:
    return yaml.safe_load(SAMPLE_GOLDEN_YAML)["examples"]


# ---------------------------------------------------------------------------
# Import under test (will fail until implementation exists — RED phase)
# ---------------------------------------------------------------------------


@pytest.fixture()
def eval_module():
    from scripts.eval import agent_routing_eval

    return agent_routing_eval


# ---------------------------------------------------------------------------
# Test: load_golden_set
# ---------------------------------------------------------------------------


class TestLoadGoldenSet:
    def test_loads_examples(self, eval_module, golden_yaml_file: Path) -> None:
        examples = eval_module.load_golden_set(golden_yaml_file)
        assert len(examples) == 4

    def test_each_example_has_required_fields(self, eval_module, golden_yaml_file: Path) -> None:
        examples = eval_module.load_golden_set(golden_yaml_file)
        for ex in examples:
            assert "id" in ex
            assert "query" in ex
            assert "route" in ex
            assert "expected_tools" in ex

    def test_missing_file_raises(self, eval_module, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            eval_module.load_golden_set(tmp_path / "nonexistent.yaml")


# ---------------------------------------------------------------------------
# Test: evaluate_blackbox
# ---------------------------------------------------------------------------


class TestEvaluateBlackbox:
    def test_passes_when_keywords_present(self, eval_module) -> None:
        example = {
            "id": 1,
            "query": "цена?",
            "answer_keywords": ["€", "апартамент"],
        }
        result = eval_module.evaluate_blackbox(
            example=example,
            actual_answer="Апартамент стоит 120 000 €",
        )
        assert result["pass"] is True
        assert result["score"] == 1.0

    def test_fails_when_keywords_missing(self, eval_module) -> None:
        example = {
            "id": 1,
            "query": "цена?",
            "answer_keywords": ["€", "апартамент"],
        }
        result = eval_module.evaluate_blackbox(
            example=example,
            actual_answer="Не нашёл информацию",
        )
        assert result["pass"] is False
        assert result["score"] < 1.0

    def test_partial_keyword_match_is_partial_score(self, eval_module) -> None:
        example = {
            "id": 1,
            "query": "цена?",
            "answer_keywords": ["€", "апартамент"],
        }
        result = eval_module.evaluate_blackbox(
            example=example,
            actual_answer="Цена в €",
        )
        # One of two keywords matched
        assert 0.0 < result["score"] < 1.0

    def test_no_keywords_always_passes(self, eval_module) -> None:
        example = {"id": 1, "query": "привет", "answer_keywords": []}
        result = eval_module.evaluate_blackbox(
            example=example,
            actual_answer="Привет!",
        )
        assert result["pass"] is True
        assert result["score"] == 1.0


# ---------------------------------------------------------------------------
# Test: evaluate_trajectory
# ---------------------------------------------------------------------------


class TestEvaluateTrajectory:
    def test_exact_match(self, eval_module) -> None:
        example = {
            "id": 1,
            "expected_tools": ["apartment_search"],
            "route": "apartment_search",
        }
        actual_calls = [{"tool": "apartment_search", "args": {"query": "квартира"}}]
        result = eval_module.evaluate_trajectory(example=example, actual_tool_calls=actual_calls)
        assert result["pass"] is True
        assert result["score"] == 1.0

    def test_missing_tool_call_fails(self, eval_module) -> None:
        example = {
            "id": 1,
            "expected_tools": ["rag_search"],
            "route": "rag_search",
        }
        result = eval_module.evaluate_trajectory(example=example, actual_tool_calls=[])
        assert result["pass"] is False
        assert result["score"] < 1.0

    def test_wrong_tool_fails(self, eval_module) -> None:
        example = {
            "id": 1,
            "expected_tools": ["rag_search"],
            "route": "rag_search",
        }
        actual_calls = [{"tool": "apartment_search", "args": {}}]
        result = eval_module.evaluate_trajectory(example=example, actual_tool_calls=actual_calls)
        assert result["pass"] is False

    def test_direct_route_no_tools_passes(self, eval_module) -> None:
        example = {
            "id": 3,
            "expected_tools": [],
            "route": "direct",
        }
        result = eval_module.evaluate_trajectory(example=example, actual_tool_calls=[])
        assert result["pass"] is True

    def test_direct_route_with_tools_fails(self, eval_module) -> None:
        example = {
            "id": 3,
            "expected_tools": [],
            "route": "direct",
        }
        actual_calls = [{"tool": "rag_search", "args": {}}]
        result = eval_module.evaluate_trajectory(example=example, actual_tool_calls=actual_calls)
        assert result["pass"] is False

    def test_extra_tool_partial_pass(self, eval_module) -> None:
        """Extra tool calls reduce score but required tool present → partial."""
        example = {
            "id": 1,
            "expected_tools": ["rag_search"],
            "route": "rag_search",
        }
        actual_calls = [
            {"tool": "rag_search", "args": {}},
            {"tool": "apartment_search", "args": {}},
        ]
        result = eval_module.evaluate_trajectory(example=example, actual_tool_calls=actual_calls)
        # Required tool is present, so at least partial credit
        assert result["score"] > 0.0


# ---------------------------------------------------------------------------
# Test: evaluate_single_step
# ---------------------------------------------------------------------------


class TestEvaluateSingleStep:
    def test_params_present_passes(self, eval_module) -> None:
        example = {
            "id": 1,
            "tool_params": {
                "apartment_search": {"query": "квартира Балчик"},
            },
        }
        actual_calls = [{"tool": "apartment_search", "args": {"query": "квартира в Балчике"}}]
        result = eval_module.evaluate_single_step(example=example, actual_tool_calls=actual_calls)
        assert result["pass"] is True

    def test_missing_param_fails(self, eval_module) -> None:
        example = {
            "id": 1,
            "tool_params": {
                "rag_search": {"query": "процедура покупки"},
            },
        }
        actual_calls = [{"tool": "rag_search", "args": {}}]
        result = eval_module.evaluate_single_step(example=example, actual_tool_calls=actual_calls)
        assert result["pass"] is False

    def test_no_tool_params_always_passes(self, eval_module) -> None:
        example = {"id": 3, "tool_params": {}}
        result = eval_module.evaluate_single_step(example=example, actual_tool_calls=[])
        assert result["pass"] is True

    def test_wrong_tool_called_fails(self, eval_module) -> None:
        example = {
            "id": 1,
            "tool_params": {
                "rag_search": {"query": "вопрос"},
            },
        }
        actual_calls = [{"tool": "apartment_search", "args": {"query": "вопрос"}}]
        result = eval_module.evaluate_single_step(example=example, actual_tool_calls=actual_calls)
        assert result["pass"] is False


# ---------------------------------------------------------------------------
# Test: compute_metrics
# ---------------------------------------------------------------------------


class TestComputeMetrics:
    def test_all_pass(self, eval_module) -> None:
        results = [
            {
                "blackbox": {"pass": True, "score": 1.0},
                "trajectory": {"pass": True, "score": 1.0},
                "single_step": {"pass": True, "score": 1.0},
            },
            {
                "blackbox": {"pass": True, "score": 1.0},
                "trajectory": {"pass": True, "score": 1.0},
                "single_step": {"pass": True, "score": 1.0},
            },
        ]
        metrics = eval_module.compute_metrics(results)
        assert metrics["blackbox_pass_rate"] == 1.0
        assert metrics["trajectory_pass_rate"] == 1.0
        assert metrics["single_step_pass_rate"] == 1.0
        assert metrics["overall_pass_rate"] == 1.0

    def test_mixed_results(self, eval_module) -> None:
        results = [
            {
                "blackbox": {"pass": True, "score": 1.0},
                "trajectory": {"pass": True, "score": 1.0},
                "single_step": {"pass": True, "score": 1.0},
            },
            {
                "blackbox": {"pass": False, "score": 0.0},
                "trajectory": {"pass": False, "score": 0.0},
                "single_step": {"pass": False, "score": 0.0},
            },
        ]
        metrics = eval_module.compute_metrics(results)
        assert metrics["blackbox_pass_rate"] == 0.5
        assert metrics["trajectory_pass_rate"] == 0.5
        assert metrics["single_step_pass_rate"] == 0.5

    def test_empty_results(self, eval_module) -> None:
        metrics = eval_module.compute_metrics([])
        assert metrics["total"] == 0
        assert metrics["blackbox_pass_rate"] == 0.0

    def test_total_count_correct(self, eval_module) -> None:
        results = [
            {
                "blackbox": {"pass": True, "score": 1.0},
                "trajectory": {"pass": True, "score": 1.0},
                "single_step": {"pass": True, "score": 1.0},
            },
        ]
        metrics = eval_module.compute_metrics(results)
        assert metrics["total"] == 1


# ---------------------------------------------------------------------------
# Test: route_from_tools
# ---------------------------------------------------------------------------


class TestRouteFromTools:
    def test_apartment_search_route(self, eval_module) -> None:
        calls = [{"tool": "apartment_search", "args": {}}]
        assert eval_module.route_from_tools(calls) == "apartment_search"

    def test_rag_search_route(self, eval_module) -> None:
        calls = [{"tool": "rag_search", "args": {}}]
        assert eval_module.route_from_tools(calls) == "rag_search"

    def test_crm_route(self, eval_module) -> None:
        calls = [{"tool": "crm_create_lead", "args": {}}]
        assert eval_module.route_from_tools(calls) == "crm_create_lead"

    def test_no_calls_direct(self, eval_module) -> None:
        assert eval_module.route_from_tools([]) == "direct"

    def test_first_tool_determines_route(self, eval_module) -> None:
        calls = [
            {"tool": "rag_search", "args": {}},
            {"tool": "apartment_search", "args": {}},
        ]
        assert eval_module.route_from_tools(calls) == "rag_search"
