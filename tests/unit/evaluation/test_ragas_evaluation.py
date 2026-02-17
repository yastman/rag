# tests/unit/evaluation/test_ragas_evaluation.py
"""Tests for RAGAS evaluation module."""

import json
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest


class TestRAGASEvaluatorInit:
    """Tests for RAGASEvaluator initialization."""

    @patch("src.evaluation.ragas_evaluation._get_evaluator_llm")
    @patch("src.evaluation.ragas_evaluation.MLflowRAGLogger")
    @patch("src.evaluation.ragas_evaluation.faithfulness")
    @patch("src.evaluation.ragas_evaluation.context_precision")
    @patch("src.evaluation.ragas_evaluation.context_recall")
    @patch("src.evaluation.ragas_evaluation.answer_relevancy")
    def test_init_creates_mlflow_logger(
        self,
        mock_answer_rel,
        mock_ctx_recall,
        mock_ctx_prec,
        mock_faith,
        mock_logger_class,
        mock_get_llm,
    ):
        """Test evaluator creates MLflow logger."""
        from src.evaluation.ragas_evaluation import RAGASEvaluator

        mock_get_llm.return_value = MagicMock()
        mock_logger = MagicMock()
        mock_logger_class.return_value = mock_logger

        evaluator = RAGASEvaluator()

        mock_logger_class.assert_called_once_with(experiment_name="ragas_quality_baseline")
        assert evaluator.mlflow_logger == mock_logger

    @patch("src.evaluation.ragas_evaluation._get_evaluator_llm")
    @patch("src.evaluation.ragas_evaluation.MLflowRAGLogger")
    @patch("src.evaluation.ragas_evaluation.faithfulness")
    @patch("src.evaluation.ragas_evaluation.context_precision")
    @patch("src.evaluation.ragas_evaluation.context_recall")
    @patch("src.evaluation.ragas_evaluation.answer_relevancy")
    def test_init_sets_metrics(
        self,
        mock_answer_rel,
        mock_ctx_recall,
        mock_ctx_prec,
        mock_faith,
        mock_logger_class,
        mock_get_llm,
    ):
        """Test evaluator initializes with RAGAS metrics."""
        from src.evaluation.ragas_evaluation import RAGASEvaluator

        mock_get_llm.return_value = MagicMock()
        mock_logger_class.return_value = MagicMock()

        evaluator = RAGASEvaluator()

        assert len(evaluator.metrics) == 4
        assert mock_faith in evaluator.metrics
        assert mock_ctx_prec in evaluator.metrics
        assert mock_ctx_recall in evaluator.metrics
        assert mock_answer_rel in evaluator.metrics


class TestEvaluatePipeline:
    """Tests for evaluate_pipeline method."""

    @pytest.fixture
    def evaluator(self):
        """Create evaluator with mocked dependencies."""
        with patch("src.evaluation.ragas_evaluation.MLflowRAGLogger") as mock_logger_class:
            with patch("src.evaluation.ragas_evaluation._get_evaluator_llm") as mock_get_llm:
                with patch("src.evaluation.ragas_evaluation.faithfulness"):
                    with patch("src.evaluation.ragas_evaluation.context_precision"):
                        with patch("src.evaluation.ragas_evaluation.context_recall"):
                            with patch("src.evaluation.ragas_evaluation.answer_relevancy"):
                                mock_get_llm.return_value = MagicMock()
                                mock_logger = MagicMock()
                                mock_logger.start_run.return_value.__enter__ = MagicMock()
                                mock_logger.start_run.return_value.__exit__ = MagicMock(
                                    return_value=False
                                )
                                mock_logger.get_run_url.return_value = "http://mlflow/run/123"
                                mock_logger_class.return_value = mock_logger

                                from src.evaluation.ragas_evaluation import RAGASEvaluator

                                yield RAGASEvaluator()

    async def test_evaluate_pipeline_loads_test_set(self, evaluator):
        """Test evaluate_pipeline loads golden test set."""
        mock_pipeline = AsyncMock()
        mock_pipeline.query.return_value = {"answer": "test", "results": []}

        test_data = {"queries": [{"query": "test query", "expected_answer": "expected"}]}

        with patch("builtins.open", mock_open(read_data=json.dumps(test_data))):
            with patch("src.evaluation.ragas_evaluation.Dataset") as mock_dataset:
                with patch("src.evaluation.ragas_evaluation.evaluate") as mock_evaluate:
                    mock_evaluate.return_value = {
                        "faithfulness": 0.9,
                        "context_precision": 0.85,
                        "context_recall": 0.92,
                        "answer_relevancy": 0.88,
                    }
                    mock_dataset.from_list.return_value = MagicMock()

                    await evaluator.evaluate_pipeline(mock_pipeline, "test_set.json")

                    mock_dataset.from_list.assert_called_once()

    async def test_evaluate_pipeline_calls_rag_pipeline(self, evaluator):
        """Test evaluate_pipeline queries RAG pipeline for each test query."""
        mock_pipeline = AsyncMock()
        mock_pipeline.query.return_value = {
            "answer": "Answer",
            "results": [{"text": "context"}],
        }

        test_data = {
            "queries": [
                {"query": "query 1", "expected_answer": "expected 1"},
                {"query": "query 2", "expected_answer": "expected 2"},
            ]
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(test_data))):
            with patch("src.evaluation.ragas_evaluation.Dataset") as mock_dataset:
                with patch("src.evaluation.ragas_evaluation.evaluate") as mock_evaluate:
                    mock_evaluate.return_value = {
                        "faithfulness": 0.9,
                        "context_precision": 0.85,
                        "context_recall": 0.92,
                        "answer_relevancy": 0.88,
                    }
                    mock_dataset.from_list.return_value = MagicMock()

                    await evaluator.evaluate_pipeline(mock_pipeline)

                    assert mock_pipeline.query.call_count == 2
                    mock_pipeline.query.assert_any_call("query 1", top_k=10)
                    mock_pipeline.query.assert_any_call("query 2", top_k=10)

    async def test_evaluate_pipeline_handles_query_errors(self, evaluator, capsys):
        """Test evaluate_pipeline handles query failures gracefully."""
        mock_pipeline = AsyncMock()
        mock_pipeline.query.side_effect = [
            Exception("Query failed"),
            {"answer": "ok", "results": []},
        ]

        test_data = {
            "queries": [
                {"query": "failing query"},
                {"query": "working query"},
            ]
        }

        with patch("builtins.open", mock_open(read_data=json.dumps(test_data))):
            with patch("src.evaluation.ragas_evaluation.Dataset") as mock_dataset:
                with patch("src.evaluation.ragas_evaluation.evaluate") as mock_evaluate:
                    mock_evaluate.return_value = {
                        "faithfulness": 0.9,
                        "context_precision": 0.85,
                        "context_recall": 0.92,
                        "answer_relevancy": 0.88,
                    }
                    mock_dataset.from_list.return_value = MagicMock()

                    await evaluator.evaluate_pipeline(mock_pipeline)

                    captured = capsys.readouterr()
                    assert "Failed query" in captured.out

    async def test_evaluate_pipeline_returns_metrics(self, evaluator):
        """Test evaluate_pipeline returns RAGAS metrics."""
        mock_pipeline = AsyncMock()
        mock_pipeline.query.return_value = {"answer": "test", "results": []}

        test_data = {"queries": [{"query": "test"}]}

        with patch("builtins.open", mock_open(read_data=json.dumps(test_data))):
            with patch("src.evaluation.ragas_evaluation.Dataset") as mock_dataset:
                with patch("src.evaluation.ragas_evaluation.evaluate") as mock_evaluate:
                    mock_evaluate.return_value = {
                        "faithfulness": 0.90,
                        "context_precision": 0.85,
                        "context_recall": 0.92,
                        "answer_relevancy": 0.88,
                    }
                    mock_dataset.from_list.return_value = MagicMock()

                    result = await evaluator.evaluate_pipeline(mock_pipeline)

                    assert result["faithfulness"] == 0.90
                    assert result["context_precision"] == 0.85
                    assert result["context_recall"] == 0.92
                    assert result["answer_relevancy"] == 0.88
                    assert "eval_duration_seconds" in result
                    assert "queries_evaluated" in result

    async def test_evaluate_pipeline_logs_to_mlflow(self, evaluator):
        """Test evaluate_pipeline logs metrics to MLflow."""
        mock_pipeline = AsyncMock()
        mock_pipeline.query.return_value = {"answer": "test", "results": []}

        test_data = {"queries": [{"query": "test"}]}

        with patch("builtins.open", mock_open(read_data=json.dumps(test_data))):
            with patch("src.evaluation.ragas_evaluation.Dataset") as mock_dataset:
                with patch("src.evaluation.ragas_evaluation.evaluate") as mock_evaluate:
                    mock_evaluate.return_value = {
                        "faithfulness": 0.90,
                        "context_precision": 0.85,
                        "context_recall": 0.92,
                        "answer_relevancy": 0.88,
                    }
                    mock_dataset.from_list.return_value = MagicMock()

                    await evaluator.evaluate_pipeline(mock_pipeline)

                    evaluator.mlflow_logger.log_metrics.assert_called_once()
                    evaluator.mlflow_logger.log_dict_artifact.assert_called_once()

    async def test_evaluate_pipeline_prints_acceptance_passed(self, evaluator, capsys):
        """Test acceptance criteria passed message."""
        mock_pipeline = AsyncMock()
        mock_pipeline.query.return_value = {"answer": "test", "results": []}

        test_data = {"queries": [{"query": "test"}]}

        with patch("builtins.open", mock_open(read_data=json.dumps(test_data))):
            with patch("src.evaluation.ragas_evaluation.Dataset") as mock_dataset:
                with patch("src.evaluation.ragas_evaluation.evaluate") as mock_evaluate:
                    # All metrics above thresholds
                    mock_evaluate.return_value = {
                        "faithfulness": 0.90,  # >= 0.85
                        "context_precision": 0.85,  # >= 0.80
                        "context_recall": 0.95,  # >= 0.90
                        "answer_relevancy": 0.88,
                    }
                    mock_dataset.from_list.return_value = MagicMock()

                    await evaluator.evaluate_pipeline(mock_pipeline)

                    captured = capsys.readouterr()
                    assert "PASSED" in captured.out

    async def test_evaluate_pipeline_prints_acceptance_failed(self, evaluator, capsys):
        """Test acceptance criteria failed message."""
        mock_pipeline = AsyncMock()
        mock_pipeline.query.return_value = {"answer": "test", "results": []}

        test_data = {"queries": [{"query": "test"}]}

        with patch("builtins.open", mock_open(read_data=json.dumps(test_data))):
            with patch("src.evaluation.ragas_evaluation.Dataset") as mock_dataset:
                with patch("src.evaluation.ragas_evaluation.evaluate") as mock_evaluate:
                    # Faithfulness below threshold
                    mock_evaluate.return_value = {
                        "faithfulness": 0.70,  # < 0.85
                        "context_precision": 0.85,
                        "context_recall": 0.95,
                        "answer_relevancy": 0.88,
                    }
                    mock_dataset.from_list.return_value = MagicMock()

                    await evaluator.evaluate_pipeline(mock_pipeline)

                    captured = capsys.readouterr()
                    assert "FAILED" in captured.out

    async def test_evaluate_pipeline_limits_queries_to_50(self, evaluator):
        """Test evaluate_pipeline limits queries to first 50."""
        mock_pipeline = AsyncMock()
        mock_pipeline.query.return_value = {"answer": "test", "results": []}

        # Create 100 queries
        test_data = {"queries": [{"query": f"query {i}"} for i in range(100)]}

        with patch("builtins.open", mock_open(read_data=json.dumps(test_data))):
            with patch("src.evaluation.ragas_evaluation.Dataset") as mock_dataset:
                with patch("src.evaluation.ragas_evaluation.evaluate") as mock_evaluate:
                    mock_evaluate.return_value = {
                        "faithfulness": 0.9,
                        "context_precision": 0.85,
                        "context_recall": 0.92,
                        "answer_relevancy": 0.88,
                    }
                    mock_dataset.from_list.return_value = MagicMock()

                    await evaluator.evaluate_pipeline(mock_pipeline)

                    # Should only call query 50 times
                    assert mock_pipeline.query.call_count == 50
