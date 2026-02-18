"""Tests for experiment runner evaluators."""

from __future__ import annotations

from types import SimpleNamespace


class TestRetrievalRecallEval:
    def test_full_recall(self):
        from scripts.run_experiment import retrieval_recall_eval

        result = retrieval_recall_eval(
            input={"query": "q"},
            output={
                "response": "a",
                "context": [
                    {"chunk_location": "seq_0", "content": "t", "score": 0.5},
                    {"chunk_location": "seq_1", "content": "t", "score": 0.4},
                ],
            },
            expected_output={"answer": "a"},
            metadata={"source_chunks": ["seq_0", "seq_1"]},
        )
        assert result.value == 1.0
        assert result.name == "retrieval_recall"

    def test_partial_recall(self):
        from scripts.run_experiment import retrieval_recall_eval

        result = retrieval_recall_eval(
            input={"query": "q"},
            output={
                "response": "a",
                "context": [{"chunk_location": "seq_0", "content": "t", "score": 0.5}],
            },
            expected_output={"answer": "a"},
            metadata={"source_chunks": ["seq_0", "seq_1"]},
        )
        assert result.value == 0.5

    def test_zero_recall(self):
        from scripts.run_experiment import retrieval_recall_eval

        result = retrieval_recall_eval(
            input={"query": "q"},
            output={"response": "a", "context": [{"chunk_location": "seq_99"}]},
            expected_output={"answer": "a"},
            metadata={"source_chunks": ["seq_0", "seq_1"]},
        )
        assert result.value == 0.0

    def test_no_expected_chunks(self):
        from scripts.run_experiment import retrieval_recall_eval

        result = retrieval_recall_eval(
            input={"query": "q"},
            output={"response": "a", "context": []},
            expected_output={"answer": "a"},
            metadata={},
        )
        assert result.value == 1.0


class TestAvgScoresEvaluator:
    def test_computes_average(self):
        from scripts.run_experiment import avg_scores_evaluator

        item_results = [
            SimpleNamespace(evaluations=[SimpleNamespace(name="retrieval_recall", value=1.0)]),
            SimpleNamespace(evaluations=[SimpleNamespace(name="retrieval_recall", value=0.5)]),
        ]
        result = avg_scores_evaluator(item_results=item_results)
        assert result.name == "composite_score"
        assert result.value == 0.75

    def test_empty_results(self):
        from scripts.run_experiment import avg_scores_evaluator

        result = avg_scores_evaluator(item_results=[])
        assert result.value == 0

    def test_ignores_other_metrics(self):
        from scripts.run_experiment import avg_scores_evaluator

        item_results = [
            SimpleNamespace(
                evaluations=[
                    SimpleNamespace(name="retrieval_recall", value=0.8),
                    SimpleNamespace(name="other_metric", value=0.1),
                ]
            ),
        ]
        result = avg_scores_evaluator(item_results=item_results)
        assert result.value == 0.8
