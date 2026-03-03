"""Tests for trace-to-dataset export script."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.export_traces_to_dataset import (
    SCORE_THRESHOLDS,
    classify_export_reasons,
    export_to_jsonl,
    export_to_langfuse,
    extract_item_data,
    fetch_exportable_traces,
    get_trace_scores,
    make_dataset_name,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace(
    trace_id: str = "trace-1",
    query: str = "test query",
    answer: str = "test answer",
    scores: dict[str, float] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=trace_id,
        input={"query": query} if query else {},
        output={"response": answer} if answer else {},
        scores=[SimpleNamespace(name=name, value=value) for name, value in (scores or {}).items()],
        timestamp="2026-02-17T12:00:00Z",
    )


def _make_observation(
    name: str = "node-retrieve",
    output: dict | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(name=name, output=output)


# ---------------------------------------------------------------------------
# get_trace_scores
# ---------------------------------------------------------------------------


class TestGetTraceScores:
    def test_extracts_numeric_scores(self):
        trace = _make_trace(scores={"judge_faithfulness": 0.8, "latency_total_ms": 1234.5})
        scores = get_trace_scores(trace)
        assert scores == {"judge_faithfulness": 0.8, "latency_total_ms": 1234.5}

    def test_skips_non_numeric(self):
        trace = SimpleNamespace(
            scores=[SimpleNamespace(name="category", value="bad")],
        )
        assert get_trace_scores(trace) == {}

    def test_empty_scores(self):
        trace = SimpleNamespace(scores=None)
        assert get_trace_scores(trace) == {}


# ---------------------------------------------------------------------------
# classify_export_reasons
# ---------------------------------------------------------------------------


class TestClassifyExportReasons:
    def test_low_faithfulness(self):
        reasons = classify_export_reasons({"judge_faithfulness": 0.3})
        assert "low_judge_faithfulness" in reasons

    def test_no_results(self):
        reasons = classify_export_reasons({"no_results": 1.0})
        assert "no_results" in reasons

    def test_good_scores_no_reasons(self):
        reasons = classify_export_reasons(
            {
                "judge_faithfulness": 0.9,
                "judge_answer_relevance": 0.85,
                "judge_context_relevance": 0.8,
            }
        )
        assert reasons == []

    def test_multiple_reasons(self):
        reasons = classify_export_reasons(
            {
                "judge_faithfulness": 0.3,
                "judge_answer_relevance": 0.4,
                "no_results": 1.0,
            }
        )
        assert len(reasons) == 3

    def test_threshold_values_match_yaml(self):
        """Thresholds should match tests/baseline/thresholds.yaml judge section."""
        assert SCORE_THRESHOLDS["judge_faithfulness"] == 0.75
        assert SCORE_THRESHOLDS["judge_answer_relevance"] == 0.70
        assert SCORE_THRESHOLDS["judge_context_relevance"] == 0.65


# ---------------------------------------------------------------------------
# extract_item_data
# ---------------------------------------------------------------------------


class TestExtractItemData:
    def test_extracts_query_and_answer(self):
        trace = _make_trace(query="hello", answer="world")
        data = extract_item_data(trace, [])
        assert data is not None
        assert data["query"] == "hello"
        assert data["answer"] == "world"

    def test_returns_none_without_query(self):
        trace = _make_trace(query="", answer="world")
        assert extract_item_data(trace, []) is None

    def test_returns_none_without_answer(self):
        trace = _make_trace(query="hello", answer="")
        assert extract_item_data(trace, []) is None

    def test_extracts_context_from_retrieve(self):
        trace = _make_trace()
        obs = _make_observation(
            name="node-retrieve",
            output={
                # node-retrieve writes eval_docs as a joined string, not retrieved_context
                "eval_docs": "[0.90] doc1\n\n[0.80] doc2",
            },
        )
        data = extract_item_data(trace, [obs])
        assert data is not None
        assert len(data["context"]) == 2
        assert any("doc1" in part for part in data["context"])

    def test_skips_non_retrieve_observations(self):
        trace = _make_trace()
        obs = _make_observation(name="node-generate", output={"text": "generated"})
        data = extract_item_data(trace, [obs])
        assert data is not None
        assert data["context"] == []


# ---------------------------------------------------------------------------
# fetch_exportable_traces
# ---------------------------------------------------------------------------


class TestFetchExportableTraces:
    def test_fetches_and_filters_low_score_traces(self):
        bad_trace = _make_trace(
            trace_id="bad-1",
            query="failing query",
            answer="bad answer",
            scores={"judge_faithfulness": 0.3},
        )
        good_trace = _make_trace(
            trace_id="good-1",
            scores={"judge_faithfulness": 0.9},
        )

        langfuse = MagicMock()
        # Page 1: two traces; Page 2: empty
        langfuse.api.trace.list.side_effect = [
            SimpleNamespace(data=[bad_trace, good_trace]),
            SimpleNamespace(data=[]),
        ]
        langfuse.api.observations.get_many.return_value = SimpleNamespace(data=[])

        items = fetch_exportable_traces(langfuse, days=7, tag="rag")

        assert len(items) == 1
        assert items[0]["trace_id"] == "bad-1"
        assert "low_judge_faithfulness" in items[0]["reasons"]

    def test_skips_traces_without_judge_scores(self):
        trace = _make_trace(scores={"latency_total_ms": 500})

        langfuse = MagicMock()
        langfuse.api.trace.list.side_effect = [
            SimpleNamespace(data=[trace]),
            SimpleNamespace(data=[]),
        ]

        items = fetch_exportable_traces(langfuse, days=7, tag="rag")
        assert len(items) == 0

    def test_paginates_through_all_pages(self):
        trace1 = _make_trace(trace_id="t1", scores={"judge_faithfulness": 0.2})
        trace2 = _make_trace(trace_id="t2", scores={"judge_faithfulness": 0.1})

        langfuse = MagicMock()
        langfuse.api.trace.list.side_effect = [
            SimpleNamespace(data=[trace1]),
            SimpleNamespace(data=[trace2]),
            SimpleNamespace(data=[]),
        ]
        langfuse.api.observations.get_many.return_value = SimpleNamespace(data=[])

        items = fetch_exportable_traces(langfuse, days=7, tag="rag")
        assert len(items) == 2
        assert langfuse.api.trace.list.call_count == 3


# ---------------------------------------------------------------------------
# export_to_langfuse
# ---------------------------------------------------------------------------


class TestExportToLangfuse:
    def test_creates_dataset_and_items(self):
        langfuse = MagicMock()
        items = [
            {
                "trace_id": "t1",
                "query": "q1",
                "answer": "a1",
                "context": ["ctx1"],
                "scores": {"judge_faithfulness": 0.3},
                "reasons": ["low_judge_faithfulness"],
            },
        ]

        count = export_to_langfuse(langfuse, "test-dataset", items)

        assert count == 1
        langfuse.create_dataset.assert_called_once_with(name="test-dataset")
        langfuse.create_dataset_item.assert_called_once()
        call_kwargs = langfuse.create_dataset_item.call_args.kwargs
        assert call_kwargs["dataset_name"] == "test-dataset"
        assert call_kwargs["input"] == {"query": "q1"}
        assert call_kwargs["expected_output"] == {"response": "a1"}
        assert call_kwargs["source_trace_id"] == "t1"
        langfuse.flush.assert_called_once()


# ---------------------------------------------------------------------------
# export_to_jsonl
# ---------------------------------------------------------------------------


class TestExportToJsonl:
    def test_writes_valid_jsonl(self, tmp_path: Path):
        items = [
            {
                "trace_id": "t1",
                "query": "q1",
                "answer": "a1",
                "context": ["ctx"],
                "scores": {"judge_faithfulness": 0.3},
                "reasons": ["low_judge_faithfulness"],
            },
            {
                "trace_id": "t2",
                "query": "q2",
                "answer": "a2",
                "context": [],
                "scores": {},
                "reasons": ["no_results"],
            },
        ]
        output = tmp_path / "test.jsonl"
        export_to_jsonl(output, items)

        lines = output.read_text().strip().split("\n")
        assert len(lines) == 2

        record = json.loads(lines[0])
        assert record["input"]["query"] == "q1"
        assert record["expected_output"]["response"] == "a1"
        assert record["metadata"]["source_trace_id"] == "t1"

    def test_creates_parent_dirs(self, tmp_path: Path):
        output = tmp_path / "nested" / "dir" / "data.jsonl"
        export_to_jsonl(output, [])
        assert output.exists()


# ---------------------------------------------------------------------------
# make_dataset_name
# ---------------------------------------------------------------------------


class TestMakeDatasetName:
    def test_default_prefix(self):
        name = make_dataset_name()
        assert name.startswith("rag-eval-")
        assert len(name) == len("rag-eval-YYYYMMDD")

    def test_custom_prefix(self):
        name = make_dataset_name(prefix="custom")
        assert name.startswith("custom-")
