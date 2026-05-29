#!/usr/bin/env python3
"""Log<->trace correlation checks for canonical end-to-end flows (#2255).

Goal (child of #2246 F6; complements #2252): prove that the logs emitted by the
canonical bot/RAG/CRM flows carry the OTEL trace/span identifiers and that they
correlate back to the flow's trace. #2217/#2239 wired the identifiers into JSON
logs; this is the validation that they actually show up for covered flows.

Dependency-light (stdlib only) so it can be unit-tested without the heavy
``scripts/validate_traces.py`` import graph; ``validate_traces.py`` imports and
calls ``check_log_correlation(...)`` so it runs as part of the existing
validator (and under ``make validate-traces-fast``).

Field-name subtlety (important): the JSON formatter in
``telegram_bot/logging_config.py`` RENAMES the OTEL LogRecord attributes
``otelTraceID``/``otelSpanID`` to the emitted JSON keys ``trace_id``/``span_id``
and treats the string ``"0"`` (OTEL "no active trace" sentinel) as absence. So a
naive Loki query for ``otelTraceID`` matches nothing — the on-disk/Loki field is
``trace_id``. This module accepts either spelling and rejects the ``"0"`` /
empty sentinel.

Status semantics (never silently pass an unproven boundary):

* ``ok``          — sampled flow logs carry the required identifiers and (when an
  expected trace id is known) match it.
* ``mismatch``    — a sampled log carries a trace id that does NOT match the
  flow's expected trace id. Correlation is broken. Hard failure for the gate.
* ``incomplete``  — logs exist for the run but none carry the identifiers (the
  traced operation may not have logged, or instrumentation is off). Reported,
  not failed.
* ``unavailable`` — no logs available to sample (e.g. local run without a log
  source). Reported, not failed.

Interpreting failures locally (no production / VPS / secrets / live CRM writes):

* Set ``LOG_CORRELATION_SOURCE`` to a newline-delimited JSON log file to enable
  the check; without it the check reports ``unavailable`` for every flow.
* ``mismatch`` is the actionable signal (a log line points at the wrong trace);
  ``incomplete``/``unavailable`` only tell you the boundary is unproven locally.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# logical field name -> accepted record keys (emitted JSON first, raw OTEL attr next)
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "otelTraceID": ("trace_id", "otelTraceID"),
    "otelSpanID": ("span_id", "otelSpanID"),
}

# Values that mean "no correlation present".
_ABSENT_VALUES = {"", "0"}

DEFAULT_REQUIRED_FIELDS: tuple[str, ...] = ("otelTraceID", "otelSpanID")


def get_correlation_value(record: Any, logical_field: str) -> str | None:
    """Return the correlation value for ``logical_field`` from a log record,
    accepting either the emitted JSON key or the raw OTEL attribute, and
    treating the ``"0"``/empty sentinel as absent."""
    keys = FIELD_ALIASES.get(logical_field, (logical_field,))
    for key in keys:
        val = record.get(key) if isinstance(record, dict) else getattr(record, key, None)
        if val is None:
            continue
        text = str(val)
        if text not in _ABSENT_VALUES:
            return text
    return None


def record_has_fields(record: Any, fields: tuple[str, ...]) -> bool:
    return all(get_correlation_value(record, f) is not None for f in fields)


@dataclass
class LogCorrelation:
    """Result of evaluating one canonical flow's log<->trace correlation."""

    flow_name: str
    required_fields: list[str]
    sampled: int = 0
    correlated: int = 0
    missing_fields: dict[str, int] = field(default_factory=dict)
    trace_id_mismatches: int = 0
    expected_trace_id: str | None = None
    status: str = "unavailable"

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def evaluate_log_correlation(
    flow_name: str,
    required_fields: tuple[str, ...],
    log_records: list[Any],
    expected_trace_id: str | None = None,
) -> LogCorrelation:
    """Evaluate whether the sampled ``log_records`` correlate to the flow trace."""
    required = list(required_fields)
    if not log_records:
        return LogCorrelation(
            flow_name=flow_name,
            required_fields=required,
            expected_trace_id=expected_trace_id,
            status="unavailable",
        )

    correlated = 0
    missing: dict[str, int] = dict.fromkeys(required, 0)
    mismatches = 0

    for rec in log_records:
        has_all = True
        for f in required:
            if get_correlation_value(rec, f) is None:
                missing[f] += 1
                has_all = False
        if has_all:
            correlated += 1
        if expected_trace_id is not None:
            tid = get_correlation_value(rec, "otelTraceID")
            if tid is not None and tid != expected_trace_id:
                mismatches += 1

    missing = {f: c for f, c in missing.items() if c}

    if mismatches:
        status = "mismatch"
    elif correlated == 0 or missing:
        status = "incomplete"
    else:
        status = "ok"

    return LogCorrelation(
        flow_name=flow_name,
        required_fields=required,
        sampled=len(log_records),
        correlated=correlated,
        missing_fields=missing,
        trace_id_mismatches=mismatches,
        expected_trace_id=expected_trace_id,
        status=status,
    )


def load_log_records(source: Path | str | None) -> list[dict[str, Any]]:
    """Load newline-delimited JSON log records from ``source``.

    Returns an empty list when ``source`` is None/missing or unreadable, and
    silently skips lines that are not valid JSON objects.
    """
    if source is None:
        return []
    p = Path(source)
    if not p.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(obj, dict):
            records.append(obj)
    return records


def check_log_correlation(
    flows: dict[str, Any],
    log_records: list[Any],
    *,
    expected_trace_ids: dict[str, str] | None = None,
    only: set[str] | None = None,
) -> list[LogCorrelation]:
    """Evaluate log<->trace correlation for each canonical flow.

    Uses each flow's ``required_log_fields`` (falling back to
    ``DEFAULT_REQUIRED_FIELDS``) and an optional per-flow expected trace id.
    """
    expected_trace_ids = expected_trace_ids or {}
    results: list[LogCorrelation] = []
    for flow_name, flow in flows.items():
        if only is not None and flow_name not in only:
            continue
        required = tuple(flow.get("required_log_fields") or DEFAULT_REQUIRED_FIELDS)
        results.append(
            evaluate_log_correlation(
                flow_name,
                required,
                log_records,
                expected_trace_id=expected_trace_ids.get(flow_name),
            )
        )
    return results


def summarize_log_correlation(results: list[LogCorrelation]) -> str:
    """Human-readable summary for the validation report."""
    if not results:
        return "log correlation: no canonical flows evaluated."

    symbols = {
        "ok": "PASS",
        "mismatch": "FAIL",
        "incomplete": "INCOMPLETE",
        "unavailable": "UNAVAILABLE",
    }
    lines = ["Log<->trace correlation (#2255):"]
    for r in results:
        line = f"  [{symbols.get(r.status, r.status.upper())}] {r.flow_name}"
        line += f" (sampled={r.sampled}, correlated={r.correlated})"
        if r.trace_id_mismatches:
            line += f" | trace_id mismatches: {r.trace_id_mismatches}"
        if r.missing_fields:
            miss = ", ".join(f"{f}:{c}" for f, c in sorted(r.missing_fields.items()))
            line += f" | records missing fields: {miss}"
        lines.append(line)
    return "\n".join(lines)


def has_log_correlation_failure(results: list[LogCorrelation]) -> bool:
    """True if any flow had a trace-id mismatch (a hard #2255 failure).
    ``incomplete``/``unavailable`` are unproven, not broken."""
    return any(r.status == "mismatch" for r in results)
