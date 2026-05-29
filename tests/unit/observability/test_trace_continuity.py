"""Unit tests for runtime trace_id continuity evaluation (#2252).

These tests exercise the pure logic in ``scripts.trace_continuity`` without a
live Langfuse stack, using a small fake client. They cover:

* loading canonical flows from ``trace_contract.yaml::end_to_end_trace_flows``,
* a continuous flow (all required spans under one trace_id) -> ``ok``,
* a fragmented flow (a required span under a different trace_id) -> ``fragmented``,
* an incomplete flow (a required span never seen) -> ``incomplete`` (explicitly
  marked, never a silent pass),
* an unavailable flow (no root trace at all) -> ``unavailable``,
* the fetch glue against a fake Langfuse client.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from scripts.trace_continuity import (
    FlowContinuity,
    check_trace_continuity,
    evaluate_flow_continuity,
    flatten_required_spans,
    load_end_to_end_trace_flows,
    summarize_continuity,
)


# --- fakes -------------------------------------------------------------------


@dataclass
class FakeObs:
    name: str
    trace_id: str


@dataclass
class FakeTrace:
    id: str
    observations: list[FakeObs]
    timestamp: datetime = datetime(2026, 5, 29, tzinfo=UTC)


class FakeTracePage:
    def __init__(self, data: list[FakeTrace]) -> None:
        self.data = data


class FakeTraceApi:
    def __init__(self, traces_by_name: dict[str, list[FakeTrace]]) -> None:
        self._by_name = traces_by_name
        self._by_id = {t.id: t for ts in traces_by_name.values() for t in ts}

    def list(self, name: str | None = None, limit: int = 5, **_: object) -> FakeTracePage:
        return FakeTracePage(self._by_name.get(name or "", []))

    def get(self, trace_id: str) -> FakeTrace:
        return self._by_id[trace_id]


class FakeObservationsPage:
    def __init__(self, data: list[FakeObs]) -> None:
        self.data = data


class FakeObservationsApi:
    def __init__(self, observations_by_name: dict[str, list[FakeObs]] | None = None) -> None:
        self._by_name = observations_by_name or {}

    def get_many(self, name: str | None = None, **_: object) -> FakeObservationsPage:
        return FakeObservationsPage(self._by_name.get(name or "", []))


class FakeApi:
    def __init__(
        self,
        trace_api: FakeTraceApi,
        observations_api: FakeObservationsApi | None = None,
    ) -> None:
        self.trace = trace_api
        self.observations = observations_api or FakeObservationsApi()


class FakeLangfuse:
    def __init__(
        self,
        traces_by_name: dict[str, list[FakeTrace]],
        observations_by_name: dict[str, list[FakeObs]] | None = None,
    ) -> None:
        self.api = FakeApi(
            FakeTraceApi(traces_by_name),
            FakeObservationsApi(observations_by_name),
        )


# --- a minimal canonical flow spec (shape mirrors trace_contract.yaml) -------

FLOW = {
    "root_family": "telegram-rag-query",
    "entry_service": "bot",
    "required_services": ["bot", "rag-api", "bge-m3-api"],
    "required_spans": {
        "root": ["telegram-rag-query"],
        "retrieval": ["rag-pipeline", "hybrid-retrieve"],
        "backend": ["bge-m3-encode-hybrid"],
    },
}

ALL_REQUIRED = [
    "telegram-rag-query",
    "rag-pipeline",
    "hybrid-retrieve",
    "bge-m3-encode-hybrid",
]


# --- pure-logic tests --------------------------------------------------------


def test_flatten_required_spans_collects_all_groups() -> None:
    assert sorted(flatten_required_spans(FLOW)) == sorted(ALL_REQUIRED)


def test_continuous_flow_is_ok() -> None:
    root = "trace-aaa"
    obs = [FakeObs(name=n, trace_id=root) for n in ALL_REQUIRED]
    result = evaluate_flow_continuity("telegram_text_rag", FLOW, obs, root)
    assert isinstance(result, FlowContinuity)
    assert result.status == "ok"
    assert result.ok is True
    assert not result.missing
    assert not result.cross_trace


def test_fragmented_flow_is_flagged() -> None:
    root = "trace-aaa"
    obs = [FakeObs(name=n, trace_id=root) for n in ALL_REQUIRED[:-1]]
    # bge-m3 span landed under a DIFFERENT trace -> propagation broke
    obs.append(FakeObs(name="bge-m3-encode-hybrid", trace_id="trace-bbb"))
    result = evaluate_flow_continuity("telegram_text_rag", FLOW, obs, root)
    assert result.status == "fragmented"
    assert result.ok is False
    assert "bge-m3-encode-hybrid" in result.cross_trace
    assert result.cross_trace["bge-m3-encode-hybrid"] == "trace-bbb"


def test_incomplete_flow_is_marked_not_silently_passed() -> None:
    root = "trace-aaa"
    # bge-m3 span never seen anywhere
    obs = [FakeObs(name=n, trace_id=root) for n in ALL_REQUIRED[:-1]]
    result = evaluate_flow_continuity("telegram_text_rag", FLOW, obs, root)
    assert result.status == "incomplete"
    assert result.ok is False
    assert result.missing == ["bge-m3-encode-hybrid"]


def test_unavailable_when_no_root_trace() -> None:
    result = evaluate_flow_continuity("telegram_text_rag", FLOW, [], None)
    assert result.status == "unavailable"
    assert result.ok is False


# --- fetch-glue tests --------------------------------------------------------


def test_check_trace_continuity_against_fake_client_ok() -> None:
    root = FakeTrace(
        id="trace-aaa",
        observations=[FakeObs(name=n, trace_id="trace-aaa") for n in ALL_REQUIRED],
    )
    lf = FakeLangfuse({"telegram-rag-query": [root]})
    flows = {"telegram_text_rag": FLOW}
    results = check_trace_continuity(lf, flows)
    assert len(results) == 1
    assert results[0].status == "ok"


def test_check_trace_continuity_unavailable_when_family_absent() -> None:
    lf = FakeLangfuse({})  # no traces for the family
    results = check_trace_continuity(lf, {"telegram_text_rag": FLOW})
    assert results[0].status == "unavailable"


def test_check_trace_continuity_detects_fragmented_sibling_trace() -> None:
    root = FakeTrace(
        id="trace-aaa",
        observations=[FakeObs(name=n, trace_id="trace-aaa") for n in ALL_REQUIRED[:-1]],
    )
    lf = FakeLangfuse(
        {"telegram-rag-query": [root]},
        {"bge-m3-encode-hybrid": [FakeObs(name="bge-m3-encode-hybrid", trace_id="trace-bbb")]},
    )
    results = check_trace_continuity(lf, {"telegram_text_rag": FLOW})
    assert results[0].status == "fragmented"
    assert results[0].cross_trace == {"bge-m3-encode-hybrid": "trace-bbb"}


def test_check_trace_continuity_only_filter() -> None:
    lf = FakeLangfuse({})
    flows = {"telegram_text_rag": FLOW, "voice_rag_api": FLOW}
    results = check_trace_continuity(lf, flows, only={"telegram_text_rag"})
    assert {r.flow_name for r in results} == {"telegram_text_rag"}


def test_summarize_continuity_mentions_status_and_flow() -> None:
    result = evaluate_flow_continuity("telegram_text_rag", FLOW, [], None)
    text = summarize_continuity([result])
    assert "telegram_text_rag" in text
    assert "unavailable" in text.lower()


# --- contract loader against the real YAML -----------------------------------


def test_load_end_to_end_trace_flows_from_contract() -> None:
    flows = load_end_to_end_trace_flows()
    # Provided by the #2248 contract surface this work stacks on.
    assert isinstance(flows, dict)
    assert "telegram_text_rag" in flows
    for required_key in ("root_family", "required_services", "required_spans"):
        assert required_key in flows["telegram_text_rag"]


def test_load_end_to_end_trace_flows_missing_file_returns_empty(tmp_path) -> None:
    missing = tmp_path / "nope.yaml"
    assert load_end_to_end_trace_flows(missing) == {}
