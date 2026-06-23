"""End-to-end single-trace flow contract (#2244).

This is a static CI gate for the runtime goal: one user workflow should appear
as one distributed Langfuse/OTEL trace. Live validation still happens through
``make validate-traces-fast`` and Langfuse-backed checks, but this contract
keeps the canonical flow matrix wired to the span catalog, service env contract,
W3C Baggage propagation, logs, and scores.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

_REQUIRED_PROPAGATION_KEYS = {
    "carrier",
    "requires_trace_context",
    "requires_baggage",
    "forbid_manual_langfuse_trace_id",
    "propagation_entrypoints",
}

_REQUIRED_LOG_FIELDS = {"otelTraceID", "otelSpanID"}


def _catalog_span_names(trace_contract: dict[str, Any]) -> set[str]:
    spans: set[str] = set(trace_contract.get("required_families", []))
    for group in trace_contract.get("spans", {}).values():
        spans.update(group)
    return spans


def _iter_flow_spans(flow: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for group in flow["required_spans"].values():
        names.update(group)
    return names


def test_end_to_end_flow_matrix_is_declared(trace_contract: dict[str, Any]) -> None:
    flows = trace_contract.get("end_to_end_trace_flows")

    assert isinstance(flows, dict) and len(flows) >= 3, (
        "trace_contract.yaml must declare at least three canonical "
        "end_to_end_trace_flows for #2244: bot/RAG, voice/RAG API, and CRM."
    )
    for flow_name in ("telegram_text_rag", "voice_rag_api", "crm_handoff_write"):
        assert flow_name in flows, f"Missing canonical #2244 flow: {flow_name}"


def test_each_flow_references_known_services(trace_contract: dict[str, Any]) -> None:
    services = trace_contract["services_with_observe"]
    service_names = set(services)

    for flow_name, flow in trace_contract["end_to_end_trace_flows"].items():
        referenced = {flow["entry_service"], *flow["required_services"]}
        unknown = referenced - service_names
        assert not unknown, (
            f"{flow_name}: references services that are not in "
            "services_with_observe: " + ", ".join(sorted(unknown))
        )


def test_each_flow_root_family_is_required(trace_contract: dict[str, Any]) -> None:
    required_families = set(trace_contract["required_families"])

    for flow_name, flow in trace_contract["end_to_end_trace_flows"].items():
        root_family = flow["root_family"]
        assert root_family in required_families, (
            f"{flow_name}: root_family {root_family!r} must be in "
            "required_families so live trace validation can find the root."
        )


def test_each_flow_required_spans_exist_in_catalog(trace_contract: dict[str, Any]) -> None:
    catalog_spans = _catalog_span_names(trace_contract)

    for flow_name, flow in trace_contract["end_to_end_trace_flows"].items():
        flow_spans = _iter_flow_spans(flow)
        missing = flow_spans - catalog_spans
        assert not missing, (
            f"{flow_name}: required_spans contain names not declared in the "
            "canonical trace catalog: " + ", ".join(sorted(missing))
        )


def test_each_flow_has_runtime_validation_shape(trace_contract: dict[str, Any]) -> None:
    score_groups = set(trace_contract["scores"])

    for flow_name, flow in trace_contract["end_to_end_trace_flows"].items():
        assert flow.get("description"), f"{flow_name}: description is required"
        assert flow.get("required_spans", {}).get("root") == [flow["root_family"]], (
            f"{flow_name}: required_spans.root must contain only root_family"
        )

        required_spans = flow["required_spans"]
        assert len(required_spans) >= 3, (
            f"{flow_name}: must cover root plus at least two downstream span groups"
        )

        score_group_refs = set(flow.get("required_score_groups", []))
        assert score_group_refs, f"{flow_name}: required_score_groups must not be empty"
        assert score_group_refs <= score_groups, f"{flow_name}: unknown score groups: " + ", ".join(
            sorted(score_group_refs - score_groups)
        )

        log_fields = set(flow.get("required_log_fields", []))
        assert log_fields >= _REQUIRED_LOG_FIELDS, (
            f"{flow_name}: required_log_fields must include otelTraceID and otelSpanID"
        )

        commands = flow.get("validation_commands", [])
        assert "make validate-traces-fast" in commands, (
            f"{flow_name}: must document make validate-traces-fast as the local "
            "runtime validation command"
        )


def test_each_flow_requires_w3c_tracecontext_and_baggage(
    trace_contract: dict[str, Any],
) -> None:
    for flow_name, flow in trace_contract["end_to_end_trace_flows"].items():
        propagation = flow.get("propagation", {})
        missing_keys = _REQUIRED_PROPAGATION_KEYS - set(propagation)
        assert not missing_keys, f"{flow_name}: propagation missing keys: " + ", ".join(
            sorted(missing_keys)
        )

        assert propagation["carrier"] == "w3c_tracecontext_baggage"
        assert propagation["requires_trace_context"] is True
        assert propagation["requires_baggage"] is True
        assert propagation["forbid_manual_langfuse_trace_id"] is True


def test_flow_propagation_entrypoints_use_baggage(
    trace_contract: dict[str, Any],
) -> None:
    for flow_name, flow in trace_contract["end_to_end_trace_flows"].items():
        entrypoints = flow["propagation"]["propagation_entrypoints"]
        assert entrypoints, f"{flow_name}: propagation_entrypoints must not be empty"

        for relative_path in entrypoints:
            source_path = REPO_ROOT / relative_path
            assert source_path.exists(), f"{flow_name}: missing entrypoint {relative_path}"

            source = source_path.read_text(encoding="utf-8")
            has_baggage = "as_baggage=True" in source or '"as_baggage": True' in source
            assert has_baggage, (
                f"{flow_name}: {relative_path} must call "
                "propagate_attributes(..., as_baggage=True) so Langfuse "
                "user/session/tags cross HTTP/service boundaries via W3C Baggage."
            )


def test_crm_flow_requires_confirmed_write_success(trace_contract: dict[str, Any]) -> None:
    crm_flow = trace_contract["end_to_end_trace_flows"]["crm_handoff_write"]

    assert crm_flow["propagation"].get("requires_confirmed_write_success") is True, (
        "crm_handoff_write must keep #2212's guard explicit: success spans/scores "
        "are valid only after confirmed Kommo writes."
    )
    assert "crm" in crm_flow["required_score_groups"]
