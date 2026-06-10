"""Contract: DEPS-10 removes obsolete Langfuse/OTel trace tests and scripts."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REMOVED_PATHS = {
    "scripts/validate_traces.py",
    "scripts/validate_trace_runtime.py",
    "scripts/validate_voice_traces.py",
    "scripts/trace_continuity.py",
    "scripts/export_traces_to_dataset.py",
    "scripts/langfuse_alert.py",
    "scripts/langfuse_triage.py",
    "scripts/setup_langfuse_dashboards.py",
    "scripts/probe/langfuse_latency_audit.py",
    "scripts/e2e/langfuse_latest_trace_audit.py",
    "scripts/e2e/langfuse_trace_validator.py",
    "scripts/audit/langfuse_inventory.py",
    "scripts/audit/trace_audit_snapshot.py",
    "tests/observability/trace_contract.yaml",
    "tests/contract/test_end_to_end_trace_flow_contract.py",
    "tests/contract/test_observability_contextvars_contract.py",
    "tests/contract/test_otel_propagators_contract.py",
    "tests/contract/test_voice_tracing_baseline_contract.py",
    "tests/unit/test_validate_traces.py",
    "tests/unit/test_validate_trace_runtime.py",
    "tests/unit/test_export_traces_to_dataset.py",
    "tests/unit/test_langfuse_triage.py",
    "tests/unit/test_validate_aggregates.py",
    "tests/unit/test_dataset_export.py",
    "tests/unit/e2e_adapters/test_litellm_judge.py",
}


def test_obsolete_observability_assets_are_removed() -> None:
    existing = [path for path in sorted(REMOVED_PATHS) if (ROOT / path).exists()]
    assert existing == []
