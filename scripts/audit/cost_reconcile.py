"""Langfuse cost reconciliation (#2223 / Epic N).

Read-only audit that aggregates ``type=GENERATION`` observations over a time
window into per-model {calls, input_tokens, output_tokens, total_cost} and
flags models with real token traffic but **zero reported cost** — the
signature of a LiteLLM cost-map gap (model present in
``docker/litellm/config.yaml`` but missing from the LiteLLM pricing map, so
``cost_details.total`` stays 0 despite traffic).

Cost is read from Langfuse v4 ``cost_details.total_cost`` / ``total_cost``
(the LiteLLM proxy populates this via ``success_callback: ["langfuse"]``),
with legacy fallbacks for older response shapes.

Usage::

    uv run python -m scripts.audit.cost_reconcile               # last 7 days
    uv run python -m scripts.audit.cost_reconcile --days 30
    uv run python -m scripts.audit.cost_reconcile --json
    uv run python -m scripts.audit.cost_reconcile --strict      # exit 1 on zero-cost models

Best-effort: a Langfuse fetch failure degrades to an empty result and never
raises. Intended for a nightly CI job that fails when a high-traffic model
reports zero cost.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


_UNKNOWN_MODEL = "unknown"
_DEFAULT_DAYS = 7
_DEFAULT_MIN_CALLS = 100


@dataclass
class ModelCost:
    """Aggregated cost/usage for a single model over the window."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_cost: float = 0.0


# ---------------------------------------------------------------------------
# Aggregation (pure)
# ---------------------------------------------------------------------------


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _obs_cost(obs: Any) -> float:
    """Read total cost from Langfuse v4 observations with legacy fallbacks."""
    cost_details = getattr(obs, "cost_details", None)
    if isinstance(cost_details, dict):
        if "total_cost" in cost_details:
            return _as_float(cost_details.get("total_cost"))
        if "total" in cost_details:
            return _as_float(cost_details.get("total"))
    total_cost = getattr(obs, "total_cost", None)
    if total_cost is not None:
        return _as_float(total_cost)
    return _as_float(getattr(obs, "calculated_total_cost", None))


def aggregate_by_model(observations: list[Any]) -> dict[str, ModelCost]:
    """Aggregate a list of GENERATION observations into per-model totals."""
    agg: dict[str, ModelCost] = {}
    for obs in observations:
        model = (
            getattr(obs, "provided_model_name", None)
            or getattr(obs, "model", None)
            or _UNKNOWN_MODEL
        )
        bucket = agg.setdefault(model, ModelCost())
        bucket.calls += 1
        usage = getattr(obs, "usage_details", None) or {}
        if isinstance(usage, dict):
            bucket.input_tokens += _as_int(usage.get("input", usage.get("prompt_tokens")))
            bucket.output_tokens += _as_int(usage.get("output", usage.get("completion_tokens")))
        bucket.total_cost += _obs_cost(obs)
    return agg


def find_zero_cost_models(agg: dict[str, ModelCost], *, min_calls: int) -> list[str]:
    """Return models with calls >= min_calls but total_cost == 0 (cost-map gap)."""
    return sorted(
        model for model, mc in agg.items() if mc.calls >= min_calls and mc.total_cost == 0.0
    )


# ---------------------------------------------------------------------------
# Remote fetch (best-effort, mocked in tests)
# ---------------------------------------------------------------------------


def fetch_generations(client: Any, *, since: datetime, until: datetime) -> list[Any]:
    """Cursor-paginate ``type=GENERATION`` observations in [since, until)."""
    out: list[Any] = []
    cursor: str | None = None
    try:
        while True:
            resp = client.api.observations.get_many(
                type="GENERATION",
                from_start_time=since,
                to_start_time=until,
                limit=100,
                cursor=cursor,
            )
            out.extend(getattr(resp, "data", []) or [])
            meta = getattr(resp, "meta", None)
            cursor = getattr(meta, "cursor", None) or getattr(meta, "next_cursor", None)
            if not cursor:
                break
        return out
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def format_report(agg: dict[str, ModelCost], *, zero_cost: list[str], days: int) -> str:
    lines = [f"# Langfuse cost reconciliation — last {days}d (#2223)", ""]
    lines.append(f"{'model':40s} {'calls':>8s} {'in_tok':>12s} {'out_tok':>12s} {'cost_usd':>12s}")
    lines.append("-" * 88)
    for model, mc in sorted(agg.items(), key=lambda kv: -kv[1].total_cost):
        lines.append(
            f"{model:40s} {mc.calls:>8d} {mc.input_tokens:>12d} "
            f"{mc.output_tokens:>12d} {mc.total_cost:>12.4f}"
        )
    lines.append("")
    if zero_cost:
        lines.append("## ZERO-COST MODELS WITH TRAFFIC (likely LiteLLM cost-map gap)")
        for m in zero_cost:
            lines.append(f"  - {m}  (calls={agg[m].calls}, cost=0.0)")
    else:
        lines.append("## No zero-cost models above the traffic threshold.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_client() -> Any | None:
    try:
        from langfuse import get_client

        client = get_client()
        return client if hasattr(client, "api") else None
    except Exception:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Langfuse cost reconciliation")
    parser.add_argument("--days", type=int, default=_DEFAULT_DAYS)
    parser.add_argument("--min-calls", type=int, default=_DEFAULT_MIN_CALLS)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when a high-traffic model reports zero cost",
    )
    args = parser.parse_args(argv)

    until = datetime.now(UTC)
    since = until - timedelta(days=args.days)

    client = _build_client()
    observations = fetch_generations(client, since=since, until=until) if client else []
    agg = aggregate_by_model(observations)
    zero_cost = find_zero_cost_models(agg, min_calls=args.min_calls)

    if args.json:
        print(
            json.dumps(
                {
                    "days": args.days,
                    "min_calls": args.min_calls,
                    "models": {
                        m: {
                            "calls": mc.calls,
                            "input_tokens": mc.input_tokens,
                            "output_tokens": mc.output_tokens,
                            "total_cost": round(mc.total_cost, 6),
                        }
                        for m, mc in agg.items()
                    },
                    "zero_cost_models": zero_cost,
                    "langfuse_reachable": client is not None,
                },
                indent=2,
            )
        )
    else:
        print(format_report(agg, zero_cost=zero_cost, days=args.days))
        if client is None:
            print("\n(note: Langfuse client unavailable — no observations fetched)")

    if args.strict and zero_cost:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
