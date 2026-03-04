"""Tests for dataset export bug fixes (#759).

Covers:
1. Field mapping: eval_docs (not retrieved_context) — line 100
2. Deduplication: trace_id as item ID — lines 209-223
3. Idempotent create: dataset creation error handling — line 206
4. Key mismatch: query (not question) in goldset_sync — line 52
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from scripts.eval.goldset_sync import sync_to_langfuse
from scripts.export_traces_to_dataset import (
    export_to_langfuse,
    extract_item_data,
)


def _make_trace(
    trace_id: str = "trace-1",
    query: str = "test query",
    answer: str = "test answer",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=trace_id,
        input={"query": query} if query else {},
        output={"response": answer} if answer else {},
        scores=[],
    )


def _make_observation(name: str = "node-retrieve", output: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(name=name, output=output)


# ---------------------------------------------------------------------------
# Bug 1: Field mapping mismatch — eval_docs vs retrieved_context
# ---------------------------------------------------------------------------


class TestExtractItemDataEvalDocs:
    def test_uses_eval_docs_field(self):
        """Bug #759-1: node-retrieve writes eval_docs string, not retrieved_context list."""
        trace = _make_trace()
        obs = _make_observation(
            name="node-retrieve",
            output={"eval_docs": "[0.90] first document\n\n[0.80] second document"},
        )
        data = extract_item_data(trace, [obs])
        assert data is not None
        assert len(data["context"]) == 2

    def test_retrieved_context_no_longer_used(self):
        """Bug #759-1: old retrieved_context field must not populate context."""
        trace = _make_trace()
        obs = _make_observation(
            name="node-retrieve",
            output={"retrieved_context": [{"content": "legacy doc"}]},
        )
        data = extract_item_data(trace, [obs])
        assert data is not None
        assert data["context"] == []

    def test_empty_eval_docs_yields_empty_context(self):
        """Empty eval_docs string gives empty context list."""
        trace = _make_trace()
        obs = _make_observation(name="node-retrieve", output={"eval_docs": ""})
        data = extract_item_data(trace, [obs])
        assert data is not None
        assert data["context"] == []

    def test_eval_docs_content_is_preserved(self):
        """Context parts must contain the document text from eval_docs."""
        trace = _make_trace()
        obs = _make_observation(
            name="node-retrieve",
            output={"eval_docs": "[0.95] article about property\n\n[0.85] tax rules"},
        )
        data = extract_item_data(trace, [obs])
        assert data is not None
        assert any("property" in part for part in data["context"])
        assert any("tax" in part for part in data["context"])


# ---------------------------------------------------------------------------
# Bug 2: No deduplication — trace_id as item ID
# ---------------------------------------------------------------------------


class TestExportToLangfuseDeduplication:
    def test_trace_id_used_as_item_id(self):
        """Bug #759-2: trace_id must be passed as dataset item id for idempotency."""
        langfuse = MagicMock()
        items = [
            {
                "trace_id": "trace-abc",
                "query": "q",
                "answer": "a",
                "context": [],
                "scores": {},
                "reasons": [],
            }
        ]
        export_to_langfuse(langfuse, "ds", items)
        call_kwargs = langfuse.create_dataset_item.call_args.kwargs
        assert call_kwargs.get("id") == "trace-abc"

    def test_each_item_uses_its_own_trace_id(self):
        """Each exported item gets its trace_id as the dataset item id."""
        langfuse = MagicMock()
        items = [
            {
                "trace_id": "t1",
                "query": "q1",
                "answer": "a1",
                "context": [],
                "scores": {},
                "reasons": [],
            },
            {
                "trace_id": "t2",
                "query": "q2",
                "answer": "a2",
                "context": [],
                "scores": {},
                "reasons": [],
            },
        ]
        export_to_langfuse(langfuse, "ds", items)
        calls = langfuse.create_dataset_item.call_args_list
        ids = [c.kwargs.get("id") for c in calls]
        assert "t1" in ids
        assert "t2" in ids


# ---------------------------------------------------------------------------
# Bug 3: No idempotent create — handles existing dataset
# ---------------------------------------------------------------------------


class TestExportToLangfuseIdempotentCreate:
    def test_does_not_raise_if_dataset_exists(self):
        """Bug #759-3: create_dataset must not raise when dataset already exists."""
        langfuse = MagicMock()
        langfuse.create_dataset.side_effect = Exception("Dataset already exists")
        items = [
            {
                "trace_id": "t1",
                "query": "q",
                "answer": "a",
                "context": [],
                "scores": {},
                "reasons": [],
            }
        ]
        # Must not raise
        count = export_to_langfuse(langfuse, "existing-dataset", items)
        assert count == 1

    def test_still_creates_items_when_dataset_exists(self):
        """Items are created even when dataset already existed."""
        langfuse = MagicMock()
        langfuse.create_dataset.side_effect = Exception("already exists")
        items = [
            {
                "trace_id": "t1",
                "query": "q",
                "answer": "a",
                "context": [],
                "scores": {},
                "reasons": [],
            }
        ]
        export_to_langfuse(langfuse, "existing-dataset", items)
        langfuse.create_dataset_item.assert_called_once()


# ---------------------------------------------------------------------------
# Bug 4: Key mismatch — query vs question in goldset_sync + run_experiment
# ---------------------------------------------------------------------------


class TestGoldsetSyncQueryKey:
    def test_uses_query_key_not_question(self):
        """Bug #759-4: goldset_sync must use 'query' key in input, not 'question'."""
        langfuse = MagicMock()
        langfuse.get_dataset.side_effect = Exception("not found")
        samples = [
            {"question": "What is X?", "ground_truth": "X is Y", "id": 1},
        ]
        sync_to_langfuse(langfuse, "test-dataset", samples)
        call_kwargs = langfuse.create_dataset_item.call_args.kwargs
        assert call_kwargs["input"] == {"query": "What is X?"}
        assert "question" not in call_kwargs["input"]

    def test_question_value_is_preserved_under_query_key(self):
        """The question text is still accessible via the query key."""
        langfuse = MagicMock()
        langfuse.get_dataset.side_effect = Exception("not found")
        samples = [
            {"question": "How much tax?", "ground_truth": "10%", "id": 2},
        ]
        sync_to_langfuse(langfuse, "test-dataset", samples)
        call_kwargs = langfuse.create_dataset_item.call_args.kwargs
        assert call_kwargs["input"]["query"] == "How much tax?"


# ---------------------------------------------------------------------------
# Bug 4 (consumer): run_experiment reads 'query' key, not 'question'
# ---------------------------------------------------------------------------


class TestRunExperimentQueryKey:
    def test_build_rag_task_reads_query_key(self):
        """Bug #759-4: build_rag_task must read 'query' from item.input, not 'question'."""
        from unittest.mock import patch

        from scripts.eval.run_experiment import build_rag_task

        with (
            patch("scripts.eval.run_experiment._build_eval_state") as mock_state,
            patch("scripts.eval.run_experiment.asyncio") as mock_asyncio,
        ):
            mock_state.return_value = {}
            mock_asyncio.run.return_value = {"response": "ok", "retrieved_context": []}

            task = build_rag_task(MagicMock())
            item = MagicMock()
            item.input = {"query": "tax question"}
            task(item=item)

            mock_state.assert_called_once_with("tax question")

    def test_build_rag_task_reads_legacy_question_key(self):
        """When input has only legacy 'question', task still builds eval state correctly."""
        from unittest.mock import patch

        from scripts.eval.run_experiment import build_rag_task

        with (
            patch("scripts.eval.run_experiment._build_eval_state") as mock_state,
            patch("scripts.eval.run_experiment.asyncio") as mock_asyncio,
        ):
            mock_state.return_value = {}
            mock_asyncio.run.return_value = {"response": "ok", "retrieved_context": []}

            task = build_rag_task(MagicMock())
            item = MagicMock()
            item.input = {"question": "legacy question key"}
            task(item=item)

            mock_state.assert_called_once_with("legacy question key")
