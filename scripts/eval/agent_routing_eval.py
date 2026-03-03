"""Agent trajectory evaluation for tool routing (#760).

Evaluates agent tool-routing accuracy at 3 levels:
  1. Black-box  — final answer contains expected keywords
  2. Trajectory — correct sequence of tool calls was made
  3. Single-step — each tool call has required parameters present

Usage (offline, no LLM required for evaluation logic):
    uv run python scripts/eval/agent_routing_eval.py
    uv run python scripts/eval/agent_routing_eval.py --golden tests/eval/agent_routing_golden.yaml
    uv run python scripts/eval/agent_routing_eval.py --golden tests/eval/agent_routing_golden.yaml \\
        --output reports/routing_eval.json

Routes evaluated:
    apartment_search  — queries about specific apartments/listings
    rag_search        — general knowledge / FAQ / legal / process
    crm_*             — CRM operations (get_deal, create_lead, add_note, …)
    direct            — chitchat, greetings, small talk (no tool call)
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import yaml


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GOLDEN_SET_DEFAULT = Path(__file__).resolve().parents[2] / "tests/eval/agent_routing_golden.yaml"

# Tool name prefixes that map to CRM route family
_CRM_PREFIXES = (
    "crm_get_deal",
    "crm_create_lead",
    "crm_update_lead",
    "crm_get_contacts",
    "crm_upsert_contact",
    "crm_add_note",
    "crm_create_task",
    "crm_link_contact_to_deal",
    "crm_search_leads",
    "crm_get_my_leads",
    "crm_get_my_tasks",
    "crm_update_contact",
)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_golden_set(path: Path | str) -> list[dict[str, Any]]:
    """Load golden set examples from a YAML file.

    Args:
        path: Path to the YAML file.

    Returns:
        List of example dicts, each with at minimum:
        ``id``, ``query``, ``route``, ``expected_tools``, ``tool_params``,
        ``answer_keywords``.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Golden set not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["examples"]


# ---------------------------------------------------------------------------
# Route helpers
# ---------------------------------------------------------------------------


def route_from_tools(tool_calls: list[dict[str, Any]]) -> str:
    """Derive the effective route from an agent's tool call list.

    The route is determined by the **first** tool called:
    - ``apartment_search`` → "apartment_search"
    - ``rag_search``       → "rag_search"
    - ``crm_*``            → exact tool name (e.g. "crm_create_lead")
    - no calls             → "direct"

    Args:
        tool_calls: List of ``{"tool": str, "args": dict}`` records.

    Returns:
        Route string.
    """
    if not tool_calls:
        return "direct"
    return tool_calls[0]["tool"]


# ---------------------------------------------------------------------------
# Level 1 — Black-box evaluation
# ---------------------------------------------------------------------------


def evaluate_blackbox(
    example: dict[str, Any],
    actual_answer: str,
) -> dict[str, Any]:
    """Evaluate whether the final answer satisfies keyword expectations.

    Score = fraction of ``answer_keywords`` found (case-insensitive) in
    ``actual_answer``.  Pass threshold: score == 1.0.

    Args:
        example: Golden set example with optional ``answer_keywords`` list.
        actual_answer: The answer string produced by the agent.

    Returns:
        Dict with ``pass`` (bool), ``score`` (float 0–1), ``details``.
    """
    keywords: list[str] = example.get("answer_keywords", [])
    if not keywords:
        return {"pass": True, "score": 1.0, "details": {"matched": [], "missing": []}}

    answer_lower = actual_answer.lower()
    matched = [kw for kw in keywords if kw.lower() in answer_lower]
    missing = [kw for kw in keywords if kw.lower() not in answer_lower]
    score = len(matched) / len(keywords)
    return {
        "pass": score == 1.0,
        "score": score,
        "details": {"matched": matched, "missing": missing},
    }


# ---------------------------------------------------------------------------
# Level 2 — Trajectory evaluation
# ---------------------------------------------------------------------------


def evaluate_trajectory(
    example: dict[str, Any],
    actual_tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate whether the agent called the correct tool(s) in order.

    Scoring:
    - No expected tools AND no actual calls → 1.0 (direct route correct)
    - No expected tools BUT actual calls made → 0.0 (false tool usage)
    - Expected tools: score = |expected ∩ actual| / |expected ∪ actual|
      (Jaccard-like; penalises both missing and extra tools)
    - Pass threshold: score == 1.0

    Args:
        example: Golden set example with ``expected_tools`` list.
        actual_tool_calls: List of ``{"tool": str, "args": dict}`` records.

    Returns:
        Dict with ``pass``, ``score``, ``details``.
    """
    expected: list[str] = example.get("expected_tools", [])
    actual_names = [c["tool"] for c in actual_tool_calls]

    # Direct route: no tools expected
    if not expected:
        if not actual_names:
            return {"pass": True, "score": 1.0, "details": {"expected": [], "actual": []}}
        return {
            "pass": False,
            "score": 0.0,
            "details": {
                "expected": [],
                "actual": actual_names,
                "reason": "expected no tool calls but agent called tools",
            },
        }

    # Compute set-based score
    expected_set = set(expected)
    actual_set = set(actual_names)
    intersection = expected_set & actual_set
    union = expected_set | actual_set
    score = len(intersection) / len(union) if union else 1.0

    return {
        "pass": score == 1.0,
        "score": score,
        "details": {
            "expected": expected,
            "actual": actual_names,
            "missing": sorted(expected_set - actual_set),
            "extra": sorted(actual_set - expected_set),
        },
    }


# ---------------------------------------------------------------------------
# Level 3 — Single-step parameter evaluation
# ---------------------------------------------------------------------------


def evaluate_single_step(
    example: dict[str, Any],
    actual_tool_calls: list[dict[str, Any]],
) -> dict[str, Any]:
    """Evaluate whether tool calls include required parameters.

    For each tool in ``tool_params``, checks that the agent called that tool
    and that every required key is present in the call's ``args``.

    Score = fraction of required (tool, param) pairs that are satisfied.
    Pass threshold: score == 1.0.

    Args:
        example: Golden set example with ``tool_params`` dict mapping
            tool_name → {param: expected_value_hint}.
        actual_tool_calls: List of ``{"tool": str, "args": dict}`` records.

    Returns:
        Dict with ``pass``, ``score``, ``details``.
    """
    tool_params: dict[str, dict[str, Any]] = example.get("tool_params", {})
    if not tool_params:
        return {"pass": True, "score": 1.0, "details": {}}

    # Index actual calls by tool name (keep last call per tool for dedup)
    actual_by_tool: dict[str, dict[str, Any]] = {}
    for call in actual_tool_calls:
        actual_by_tool[call["tool"]] = call.get("args", {})

    total_required = 0
    total_satisfied = 0
    details: dict[str, Any] = {}

    for tool_name, required_params in tool_params.items():
        if not required_params:
            continue
        if tool_name not in actual_by_tool:
            # Tool not called at all — all params unsatisfied
            total_required += len(required_params)
            details[tool_name] = {
                "error": "tool not called",
                "required": list(required_params.keys()),
                "present": [],
            }
            continue

        actual_args = actual_by_tool[tool_name]
        present = []
        missing = []
        for param in required_params:
            total_required += 1
            if param in actual_args and actual_args[param] is not None:
                total_satisfied += 1
                present.append(param)
            else:
                missing.append(param)

        details[tool_name] = {"present": present, "missing": missing}

    score = total_satisfied / total_required if total_required > 0 else 1.0
    return {
        "pass": score == 1.0,
        "score": score,
        "details": details,
    }


# ---------------------------------------------------------------------------
# Metrics aggregation
# ---------------------------------------------------------------------------


def compute_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate per-example eval results into summary metrics.

    Args:
        results: List of per-example dicts, each containing:
            ``blackbox``, ``trajectory``, ``single_step`` sub-dicts with
            ``pass`` and ``score`` fields.

    Returns:
        Dict with pass rates and score averages per level, plus ``total`` and
        ``overall_pass_rate`` (all 3 levels pass).
    """
    total = len(results)
    if total == 0:
        return {
            "total": 0,
            "blackbox_pass_rate": 0.0,
            "trajectory_pass_rate": 0.0,
            "single_step_pass_rate": 0.0,
            "blackbox_avg_score": 0.0,
            "trajectory_avg_score": 0.0,
            "single_step_avg_score": 0.0,
            "overall_pass_rate": 0.0,
        }

    bb_passes = sum(1 for r in results if r["blackbox"]["pass"])
    traj_passes = sum(1 for r in results if r["trajectory"]["pass"])
    ss_passes = sum(1 for r in results if r["single_step"]["pass"])
    all_passes = sum(
        1
        for r in results
        if r["blackbox"]["pass"] and r["trajectory"]["pass"] and r["single_step"]["pass"]
    )

    bb_score = sum(r["blackbox"]["score"] for r in results) / total
    traj_score = sum(r["trajectory"]["score"] for r in results) / total
    ss_score = sum(r["single_step"]["score"] for r in results) / total

    return {
        "total": total,
        "blackbox_pass_rate": bb_passes / total,
        "trajectory_pass_rate": traj_passes / total,
        "single_step_pass_rate": ss_passes / total,
        "blackbox_avg_score": bb_score,
        "trajectory_avg_score": traj_score,
        "single_step_avg_score": ss_score,
        "overall_pass_rate": all_passes / total,
    }


# ---------------------------------------------------------------------------
# Offline dry-run evaluation (mock agent responses)
# ---------------------------------------------------------------------------


def _mock_agent_run(example: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
    """Simulate agent response for offline evaluation without a live LLM.

    Returns a plausible (answer, tool_calls) pair based on the example route.
    Used in ``--dry-run`` / CI mode.
    """
    route = example.get("route", "direct")
    expected_tools = example.get("expected_tools", [])

    if route == "direct":
        answer = "Привет! Рад помочь. Please — конечно, English я понимаю :)"
        return answer, []

    tool_calls: list[dict[str, Any]] = []
    for tool_name in expected_tools:
        params = example.get("tool_params", {}).get(tool_name, {})
        tool_calls.append({"tool": tool_name, "args": params})

    # Construct a synthetic answer that includes expected keywords
    keywords = example.get("answer_keywords", [])
    answer = "Результат: " + " ".join(keywords) if keywords else "Обработано."
    return answer, tool_calls


def run_eval(
    golden_path: Path | str = GOLDEN_SET_DEFAULT,
    dry_run: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run evaluation over the golden set.

    Args:
        golden_path: Path to golden set YAML.
        dry_run: If True, uses ``_mock_agent_run`` instead of a live agent.

    Returns:
        Tuple of (per_example_results, summary_metrics).
    """
    examples = load_golden_set(golden_path)
    per_example: list[dict[str, Any]] = []

    for ex in examples:
        if dry_run:
            answer, tool_calls = _mock_agent_run(ex)
        else:
            raise NotImplementedError(
                "Live agent evaluation requires a running LiteLLM proxy. "
                "Use --dry-run for offline testing."
            )

        bb = evaluate_blackbox(ex, answer)
        traj = evaluate_trajectory(ex, tool_calls)
        ss = evaluate_single_step(ex, tool_calls)

        per_example.append(
            {
                "id": ex["id"],
                "query": ex["query"],
                "route": ex.get("route"),
                "actual_route": route_from_tools(tool_calls),
                "blackbox": bb,
                "trajectory": traj,
                "single_step": ss,
            }
        )

    metrics = compute_metrics(per_example)
    return per_example, metrics


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate agent tool-routing accuracy against a golden set.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--golden",
        default=str(GOLDEN_SET_DEFAULT),
        help="Path to golden set YAML file.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional path to write JSON results.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Use mock agent (no live LLM required). Default: True.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print per-example results.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point.

    Returns:
        Exit code: 0 if overall_pass_rate >= 0.8, else 1.
    """
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    args = _build_parser().parse_args(argv)

    per_example, metrics = run_eval(
        golden_path=args.golden,
        dry_run=args.dry_run,
    )

    if args.verbose:
        for r in per_example:
            status = "✓" if r["trajectory"]["pass"] else "✗"
            print(
                f"[{status}] #{r['id']:02d} {r['query'][:55]!r:<58} "
                f"route={r['route']!r} traj={r['trajectory']['score']:.2f} "
                f"bb={r['blackbox']['score']:.2f} ss={r['single_step']['score']:.2f}"
            )

    print("\n── Routing Eval Metrics ─────────────────────────────")
    print(f"  Total examples  : {metrics['total']}")
    print(
        f"  Blackbox        : {metrics['blackbox_pass_rate']:.0%} pass  (avg {metrics['blackbox_avg_score']:.2f})"
    )
    print(
        f"  Trajectory      : {metrics['trajectory_pass_rate']:.0%} pass  (avg {metrics['trajectory_avg_score']:.2f})"
    )
    print(
        f"  Single-step     : {metrics['single_step_pass_rate']:.0%} pass  (avg {metrics['single_step_avg_score']:.2f})"
    )
    print(f"  Overall         : {metrics['overall_pass_rate']:.0%} pass")
    print("─────────────────────────────────────────────────────\n")

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps({"metrics": metrics, "examples": per_example}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info("Results written to %s", out_path)

    pass_threshold = 0.8
    if metrics["overall_pass_rate"] < pass_threshold:
        logger.warning(
            "Overall pass rate %.0f%% below threshold %.0f%%",
            metrics["overall_pass_rate"] * 100,
            pass_threshold * 100,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
