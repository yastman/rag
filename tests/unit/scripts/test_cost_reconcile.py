"""Unit tests for scripts/audit/cost_reconcile.py (#2223 / Epic N).

We track cost via usage_details / cost_details on every generation, and the
LiteLLM proxy emits success_callback: ["langfuse"]. But we have no routine
check that the cost Langfuse reports actually reflects real provider spend.

Failure modes this audit catches:
* a model in docker/litellm/config.yaml NOT in the LiteLLM cost map ->
  silent zero-cost (cost_details.total == 0 despite real token traffic);
* a typo'd / renamed model that stops accumulating cost.

The script aggregates type=GENERATION observations over a window into
per-model {calls, input_tokens, output_tokens, total_cost} and flags models
with traffic (calls >= threshold) but zero cost.

These tests pin the pure functions; the live Langfuse fetch is mocked.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


cr = pytest.importorskip(
    "scripts.audit.cost_reconcile",
    reason="cost reconcile script under test",
)


def _obs(model, *, in_tok=0, out_tok=0, total_cost=0.0):
    """Build an ObservationsView-like object."""
    return SimpleNamespace(
        type="GENERATION",
        model=model,
        usage_details={"input": in_tok, "output": out_tok, "total": in_tok + out_tok},
        cost_details={"total": total_cost},
        calculated_total_cost=total_cost,
    )


class TestAggregateByModel:
    def test_sums_calls_tokens_cost_per_model(self) -> None:
        observations = [
            _obs("gpt-4o", in_tok=100, out_tok=50, total_cost=0.01),
            _obs("gpt-4o", in_tok=200, out_tok=100, total_cost=0.02),
            _obs("voyage-3", in_tok=300, out_tok=0, total_cost=0.005),
        ]
        agg = cr.aggregate_by_model(observations)
        assert agg["gpt-4o"].calls == 2
        assert agg["gpt-4o"].input_tokens == 300
        assert agg["gpt-4o"].output_tokens == 150
        assert agg["gpt-4o"].total_cost == pytest.approx(0.03)
        assert agg["voyage-3"].calls == 1
        assert agg["voyage-3"].total_cost == pytest.approx(0.005)

    def test_handles_missing_cost_details(self) -> None:
        obs = SimpleNamespace(
            type="GENERATION",
            model="m",
            usage_details=None,
            cost_details=None,
            calculated_total_cost=None,
        )
        agg = cr.aggregate_by_model([obs])
        assert agg["m"].calls == 1
        assert agg["m"].total_cost == 0.0
        assert agg["m"].input_tokens == 0

    def test_falls_back_to_calculated_total_cost(self) -> None:
        obs = SimpleNamespace(
            type="GENERATION",
            model="m",
            usage_details={"input": 1, "output": 1},
            cost_details=None,
            calculated_total_cost=0.42,
        )
        agg = cr.aggregate_by_model([obs])
        assert agg["m"].total_cost == pytest.approx(0.42)

    def test_groups_none_model_under_unknown(self) -> None:
        agg = cr.aggregate_by_model([_obs(None, in_tok=10, total_cost=0.0)])
        assert "unknown" in agg


class TestFindZeroCostModels:
    def test_flags_model_with_traffic_but_no_cost(self) -> None:
        agg = {
            "good": cr.ModelCost(calls=200, input_tokens=1000, output_tokens=500, total_cost=1.5),
            "broken": cr.ModelCost(calls=300, input_tokens=2000, output_tokens=900, total_cost=0.0),
            "low-traffic": cr.ModelCost(calls=5, input_tokens=50, output_tokens=10, total_cost=0.0),
        }
        flagged = cr.find_zero_cost_models(agg, min_calls=100)
        assert "broken" in flagged
        assert "good" not in flagged  # has cost
        assert "low-traffic" not in flagged  # below threshold

    def test_no_flags_when_all_priced(self) -> None:
        agg = {"m": cr.ModelCost(calls=500, input_tokens=1, output_tokens=1, total_cost=2.0)}
        assert cr.find_zero_cost_models(agg, min_calls=100) == []


class TestFetchGenerations:
    def test_cursor_pagination(self) -> None:
        client = MagicMock()
        page1 = MagicMock()
        page1.data = [_obs("gpt-4o", total_cost=0.01)]
        page1.meta = SimpleNamespace(next_cursor="cur2")
        page2 = MagicMock()
        page2.data = [_obs("voyage-3", total_cost=0.002)]
        page2.meta = SimpleNamespace(next_cursor=None)
        client.api.observations.get_many.side_effect = [page1, page2]

        from datetime import datetime

        items = cr.fetch_generations(client, since=datetime(2026, 5, 1), until=datetime(2026, 5, 8))
        assert len(items) == 2
        assert client.api.observations.get_many.call_count == 2
        # type=GENERATION filter must be passed
        first_call = client.api.observations.get_many.call_args_list[0]
        assert first_call.kwargs.get("type") == "GENERATION"

    def test_returns_empty_on_error(self) -> None:
        from datetime import datetime

        client = MagicMock()
        client.api.observations.get_many.side_effect = RuntimeError("down")
        assert (
            cr.fetch_generations(client, since=datetime(2026, 5, 1), until=datetime(2026, 5, 8))
            == []
        )


class TestFormatReport:
    def test_report_lists_models_and_flags(self) -> None:
        agg = {
            "gpt-4o": cr.ModelCost(calls=10, input_tokens=100, output_tokens=50, total_cost=0.5),
            "broken": cr.ModelCost(calls=300, input_tokens=900, output_tokens=100, total_cost=0.0),
        }
        report = cr.format_report(agg, zero_cost=["broken"], days=7)
        assert "gpt-4o" in report
        assert "broken" in report
        assert "ZERO-COST" in report.upper() or "zero-cost" in report
