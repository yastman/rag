#!/usr/bin/env python3
"""Runtime trace_id continuity checks for canonical end-to-end flows (#2252).

Goal (child of #2246 F4, core of the #2244 single-trace gate): prove that each
canonical workflow keeps **one** stable trace tree across process and thread
boundaries, instead of fragmenting into several partial Langfuse traces.

This module is intentionally dependency-light (stdlib + PyYAML) so it can be
unit-tested without the heavy ``scripts/validate_traces.py`` import graph
(langfuse, numpy, tenacity, ...). ``validate_traces.py`` imports and calls
``check_trace_continuity(...)`` so the check runs as part of the existing
validator (and therefore under ``make validate-traces-fast``) rather than as a
separate ad-hoc checker.

Status semantics (never silently pass an unproven boundary):

* ``ok``          — every required span for the flow is present under the root
  trace_id; the workflow is a single trace tree.
* ``fragmented``  — a required span exists but under a *different* trace_id than
  the root. Propagation broke across a service/thread boundary. This is a hard
  failure for the #2244 gate.
* ``incomplete``  — a required span was not observed at all. The boundary was
  not exercised in this run (e.g. a downstream service was not running
  locally). Reported explicitly, not treated as success.
* ``unavailable`` — no root trace was found for the flow (no runtime data).
  Reported explicitly, not treated as success.

Interpreting failures locally (no production / VPS / secrets / live CRM writes):

* ``incomplete`` / ``unavailable`` are expected when you only run a subset of
  services locally; they tell you which boundary is unproven, not that the code
  is broken.
* ``fragmented`` is the actionable signal: it means trace context (W3C
  TraceContext + Baggage) was lost on a real boundary and must be fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


TRACE_CONTRACT_PATH = (
    Path(__file__).resolve().parent.parent / "tests" / "observability" / "trace_contract.yaml"
)
_FRAGMENT_LOOKBACK = timedelta(minutes=5)
_FRAGMENT_LOOKAHEAD = timedelta(minutes=15)


def load_end_to_end_trace_flows(path: Path | str = TRACE_CONTRACT_PATH) -> dict[str, Any]:
    """Load the ``end_to_end_trace_flows`` mapping from the trace contract.

    Returns an empty dict when the file or key is absent so callers can degrade
    gracefully instead of raising.
    """
    p = Path(path)
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    flows = data.get("end_to_end_trace_flows", {})
    return flows if isinstance(flows, dict) else {}


def flatten_required_spans(flow: dict[str, Any]) -> list[str]:
    """Flatten the grouped ``required_spans`` of a flow into a flat name list."""
    names: list[str] = []
    for group in (flow.get("required_spans") or {}).values():
        names.extend(group)
    return names


@dataclass
class FlowContinuity:
    """Result of evaluating one canonical flow's trace continuity."""

    flow_name: str
    root_family: str
    root_trace_id: str | None
    present: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    cross_trace: dict[str, str] = field(default_factory=dict)
    status: str = "unavailable"

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def _obs_attr(obs: Any, name: str) -> Any:
    if isinstance(obs, dict):
        return obs.get(name)
    return getattr(obs, name, None)


def evaluate_flow_continuity(
    flow_name: str,
    flow: dict[str, Any],
    observations: list[Any],
    root_trace_id: str | None,
) -> FlowContinuity:
    """Evaluate whether ``flow``'s required spans form one trace tree.

    Args:
        flow_name: canonical flow key (e.g. ``telegram_text_rag``).
        flow: the flow spec from ``end_to_end_trace_flows``.
        observations: objects/dicts exposing ``name`` and ``trace_id``. May
            include observations from sibling traces to enable fragmentation
            detection.
        root_trace_id: trace id of the flow's root trace, or ``None`` if no
            root trace was found.
    """
    required = flatten_required_spans(flow)

    seen: dict[str, set[str]] = {}
    for obs in observations:
        name = _obs_attr(obs, "name")
        if not name:
            continue
        tid = _obs_attr(obs, "trace_id")
        seen.setdefault(name, set()).add(tid)

    present: list[str] = []
    missing: list[str] = []
    cross_trace: dict[str, str] = {}

    for span in required:
        tids = seen.get(span)
        if not tids:
            missing.append(span)
            continue
        if root_trace_id is None:
            # No root anchor; record presence but cannot assert continuity.
            present.append(span)
            continue
        if root_trace_id in tids:
            present.append(span)
            others = sorted(t for t in tids if t and t != root_trace_id)
            if others:
                cross_trace[span] = others[0]
        else:
            # Span exists only under a different trace -> fragmented boundary.
            other = sorted(t for t in tids if t)
            cross_trace[span] = other[0] if other else "<unknown>"

    if root_trace_id is None:
        status = "unavailable"
    elif cross_trace:
        status = "fragmented"
    elif missing:
        status = "incomplete"
    else:
        status = "ok"

    return FlowContinuity(
        flow_name=flow_name,
        root_family=str(flow.get("root_family", "")),
        root_trace_id=root_trace_id,
        present=present,
        missing=missing,
        cross_trace=cross_trace,
        status=status,
    )


def fetch_flow_observations(
    lf: Any, root_family: str, limit: int = 5
) -> tuple[str | None, list[Any]]:
    """Fetch the most recent root trace for ``root_family`` and its observations.

    Returns ``(root_trace_id, observations)``. Degrades to ``(None, [])`` on any
    API error or when no trace exists, so a missing boundary is reported as
    ``unavailable`` rather than crashing the validator.
    """
    try:
        page = lf.api.trace.list(name=root_family, limit=limit)
    except Exception:
        return None, []
    traces = list(getattr(page, "data", None) or [])
    if not traces:
        return None, []
    root = traces[0]
    root_id = getattr(root, "id", None) or getattr(root, "trace_id", None)
    if not root_id:
        return None, []
    root_timestamp = getattr(root, "timestamp", None)
    try:
        full = lf.api.trace.get(root_id)
    except Exception:
        return root_id, []
    observations = list(getattr(full, "observations", None) or [])
    normalized = [
        {
            "name": _obs_attr(o, "name"),
            "trace_id": _obs_attr(o, "trace_id") or root_id,
        }
        for o in observations
    ]

    # Trace.get(root_id) only returns observations already attached to the root
    # trace. To distinguish "missing" from "fragmented", also look for required
    # span names that appeared in nearby sibling traces. Keep this bounded to
    # the root trace time window to avoid old observations causing false alarms.
    seen_names = {obs["name"] for obs in normalized if obs.get("name")}
    try:
        flows = load_end_to_end_trace_flows()
        required_names = {
            span
            for flow in flows.values()
            if str(flow.get("root_family", "")) == root_family
            for span in flatten_required_spans(flow)
        }
        missing_names = sorted(required_names - seen_names)
        if root_timestamp is not None and missing_names:
            for span_name in missing_names:
                page = lf.api.observations.get_many(
                    name=span_name,
                    from_start_time=root_timestamp - _FRAGMENT_LOOKBACK,
                    to_start_time=root_timestamp + _FRAGMENT_LOOKAHEAD,
                    limit=20,
                )
                for obs in getattr(page, "data", []) or []:
                    trace_id = _obs_attr(obs, "trace_id")
                    if trace_id and trace_id != root_id:
                        normalized.append({"name": _obs_attr(obs, "name"), "trace_id": trace_id})
    except Exception:
        # Fragment search is best-effort; the root trace still provides an
        # explicit incomplete/unavailable result instead of a silent pass.
        return root_id, normalized
    return root_id, normalized


def check_trace_continuity(
    lf: Any,
    flows: dict[str, Any],
    *,
    only: set[str] | None = None,
) -> list[FlowContinuity]:
    """Evaluate trace_id continuity for each canonical flow via ``lf``.

    Args:
        lf: a Langfuse client (duck-typed: ``lf.api.trace.list/get``).
        flows: ``end_to_end_trace_flows`` mapping.
        only: optional subset of flow names to evaluate.
    """
    results: list[FlowContinuity] = []
    for flow_name, flow in flows.items():
        if only is not None and flow_name not in only:
            continue
        root_family = str(flow.get("root_family", ""))
        root_id, observations = fetch_flow_observations(lf, root_family)
        results.append(evaluate_flow_continuity(flow_name, flow, observations, root_id))
    return results


def summarize_continuity(results: list[FlowContinuity]) -> str:
    """Human-readable summary for the validation report."""
    if not results:
        return "trace continuity: no canonical flows evaluated."

    symbols = {
        "ok": "PASS",
        "fragmented": "FAIL",
        "incomplete": "INCOMPLETE",
        "unavailable": "UNAVAILABLE",
    }
    lines = ["Trace continuity (single-trace gate #2244):"]
    for r in results:
        line = f"  [{symbols.get(r.status, r.status.upper())}] {r.flow_name} (root={r.root_family})"
        if r.cross_trace:
            broken = ", ".join(f"{span}->{tid}" for span, tid in sorted(r.cross_trace.items()))
            line += f" | fragmented spans: {broken}"
        if r.missing:
            line += f" | unproven spans: {', '.join(r.missing)}"
        lines.append(line)
    return "\n".join(lines)


def has_continuity_failure(results: list[FlowContinuity]) -> bool:
    """True if any flow fragmented (a hard #2244 failure). ``incomplete`` /
    ``unavailable`` do not count — they are unproven, not broken."""
    return any(r.status == "fragmented" for r in results)
