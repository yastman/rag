# tests/unit/evaluation/test_mlflow_experiments.py
"""Tests for MLflow A/B testing experiments framework."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.evaluation.mlflow_experiments import RAGExperimentRunner


class TestRAGExperimentRunnerInit:
    """Tests for RAGExperimentRunner initialization."""

    @patch("src.evaluation.mlflow_experiments.MLflowRAGLogger")
    def test_init_creates_logger(self, mock_logger_class, capsys):
        """Test runner creates MLflow logger with experiment name."""
        mock_logger = MagicMock()
        mock_logger.tracking_uri = "http://localhost:5000"
        mock_logger_class.return_value = mock_logger

        runner = RAGExperimentRunner(experiment_name="test_exp")

        mock_logger_class.assert_called_once_with(experiment_name="test_exp")
        assert runner.experiment_name == "test_exp"
        assert runner.logger == mock_logger

    @patch("src.evaluation.mlflow_experiments.MLflowRAGLogger")
    def test_init_default_experiment_name(self, mock_logger_class, capsys):
        """Test runner uses default experiment name."""
        mock_logger = MagicMock()
        mock_logger.tracking_uri = "http://localhost:5000"
        mock_logger_class.return_value = mock_logger

        runner = RAGExperimentRunner()

        mock_logger_class.assert_called_once_with(experiment_name="contextual_rag_ab_tests")
        assert runner.experiment_name == "contextual_rag_ab_tests"

    @patch("src.evaluation.mlflow_experiments.MLflowRAGLogger")
    def test_init_prints_info(self, mock_logger_class, capsys):
        """Test runner prints initialization info."""
        mock_logger = MagicMock()
        mock_logger.tracking_uri = "http://localhost:5000"
        mock_logger_class.return_value = mock_logger

        RAGExperimentRunner(experiment_name="my_exp")

        captured = capsys.readouterr()
        assert "Experiment Runner initialized" in captured.out
        assert "my_exp" in captured.out
        assert "http://localhost:5000" in captured.out


class TestRunABTest:
    """Tests for run_ab_test method."""

    @pytest.fixture
    def runner(self):
        """Create runner with mocked logger."""
        with patch("src.evaluation.mlflow_experiments.MLflowRAGLogger") as mock_logger_class:
            mock_logger = MagicMock()
            mock_logger.tracking_uri = "http://localhost:5000"
            mock_logger.start_run.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_logger.start_run.return_value.__exit__ = MagicMock(return_value=False)
            mock_logger_class.return_value = mock_logger
            yield RAGExperimentRunner(experiment_name="test")

    async def test_run_ab_test_calls_both_variants(self, runner):
        """Test run_ab_test runs both variants."""
        test_queries = [{"query": "test", "expected_article": 1}]

        with patch.object(runner, "_run_variant", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                "recall_at_1": 0.90,
                "ndcg_at_10": 0.95,
                "latency_p95_ms": 400,
            }

            await runner.run_ab_test(
                test_name="test",
                variant_a={"config_a": True},
                variant_b={"config_b": True},
                test_queries=test_queries,
            )

            assert mock_run.call_count == 2

    async def test_run_ab_test_returns_comparison(self, runner):
        """Test run_ab_test returns comparison results."""
        test_queries = [{"query": "test"}]

        with patch.object(runner, "_run_variant", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = [
                {"recall_at_1": 0.95, "ndcg_at_10": 0.90, "latency_p95_ms": 400},
                {"recall_at_1": 0.85, "ndcg_at_10": 0.88, "latency_p95_ms": 350},
            ]

            result = await runner.run_ab_test(
                test_name="test",
                variant_a={"a": 1},
                variant_b={"b": 2},
                test_queries=test_queries,
            )

            assert "winner" in result
            assert "reason" in result
            assert "variant_a" in result
            assert "variant_b" in result
            assert "delta" in result

    async def test_run_ab_test_custom_variant_names(self, runner):
        """Test run_ab_test uses custom variant names."""
        test_queries = [{"query": "test"}]

        with patch.object(runner, "_run_variant", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                "recall_at_1": 0.90,
                "ndcg_at_10": 0.95,
                "latency_p95_ms": 400,
            }

            await runner.run_ab_test(
                test_name="test",
                variant_a={"a": 1},
                variant_b={"b": 2},
                test_queries=test_queries,
                variant_a_name="With Context",
                variant_b_name="No Context",
            )

            # Verify variant names were passed
            calls = mock_run.call_args_list
            assert calls[0][1]["variant_name"] == "With Context"
            assert calls[1][1]["variant_name"] == "No Context"

    async def test_run_ab_test_prints_results(self, runner, capsys):
        """Test run_ab_test prints test results."""
        test_queries = [{"query": "test"}]

        with patch.object(runner, "_run_variant", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = {
                "recall_at_1": 0.90,
                "ndcg_at_10": 0.95,
                "latency_p95_ms": 400,
            }

            await runner.run_ab_test(
                test_name="my_test",
                variant_a={"a": 1},
                variant_b={"b": 2},
                test_queries=test_queries,
            )

            captured = capsys.readouterr()
            assert "A/B TEST:" in captured.out
            assert "my_test" in captured.out
            assert "Winner" in captured.out


class TestRunVariant:
    """Tests for _run_variant method."""

    @pytest.fixture
    def runner(self):
        """Create runner with mocked logger."""
        with patch("src.evaluation.mlflow_experiments.MLflowRAGLogger") as mock_logger_class:
            mock_logger = MagicMock()
            mock_logger.tracking_uri = "http://localhost:5000"
            mock_logger.start_run.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_logger.start_run.return_value.__exit__ = MagicMock(return_value=False)
            mock_logger_class.return_value = mock_logger
            yield RAGExperimentRunner(experiment_name="test")

    async def test_run_variant_starts_mlflow_run(self, runner):
        """Test _run_variant starts MLflow run with correct tags."""
        with patch.object(runner, "_simulate_evaluation", new_callable=AsyncMock) as mock_eval:
            mock_eval.return_value = {"recall_at_1": 0.9, "latency_p95_ms": 400}

            await runner._run_variant(
                test_name="test1",
                variant_name="A",
                variant_config={"key": "value"},
                test_queries=[],
            )

            runner.logger.start_run.assert_called_once()
            call_kwargs = runner.logger.start_run.call_args[1]
            assert "test1" in call_kwargs["run_name"]
            assert call_kwargs["tags"]["test"] == "test1"
            assert call_kwargs["tags"]["variant"] == "A"
            assert call_kwargs["tags"]["test_type"] == "ab_test"

    async def test_run_variant_logs_config(self, runner):
        """Test _run_variant logs variant config."""
        with patch.object(runner, "_simulate_evaluation", new_callable=AsyncMock) as mock_eval:
            mock_eval.return_value = {"recall_at_1": 0.9, "latency_p95_ms": 400}

            await runner._run_variant(
                test_name="test",
                variant_name="A",
                variant_config={"chunk_size": 400},
                test_queries=[],
            )

            runner.logger.log_config.assert_called_once_with(
                {"chunk_size": 400}, prefix="variant_A."
            )

    async def test_run_variant_logs_metrics(self, runner):
        """Test _run_variant logs evaluation metrics."""
        with patch.object(runner, "_simulate_evaluation", new_callable=AsyncMock) as mock_eval:
            metrics = {"recall_at_1": 0.95, "latency_p95_ms": 420}
            mock_eval.return_value = metrics

            await runner._run_variant(
                test_name="test",
                variant_name="B",
                variant_config={},
                test_queries=[],
            )

            runner.logger.log_metrics.assert_called_once_with(metrics)

    async def test_run_variant_returns_metrics(self, runner):
        """Test _run_variant returns evaluation metrics."""
        with patch.object(runner, "_simulate_evaluation", new_callable=AsyncMock) as mock_eval:
            expected = {"recall_at_1": 0.92, "ndcg_at_10": 0.88, "latency_p95_ms": 380}
            mock_eval.return_value = expected

            result = await runner._run_variant(
                test_name="test",
                variant_name="A",
                variant_config={},
                test_queries=[],
            )

            assert result == expected


class TestSimulateEvaluation:
    """Tests for _simulate_evaluation method."""

    @pytest.fixture
    def runner(self):
        """Create runner with mocked logger."""
        with patch("src.evaluation.mlflow_experiments.MLflowRAGLogger") as mock_logger_class:
            mock_logger = MagicMock()
            mock_logger.tracking_uri = "http://localhost:5000"
            mock_logger_class.return_value = mock_logger
            yield RAGExperimentRunner(experiment_name="test")

    async def test_simulate_evaluation_returns_metrics(self, runner):
        """Test _simulate_evaluation returns all expected metrics."""
        result = await runner._simulate_evaluation({}, [{"query": "test"}])

        expected_keys = [
            "recall_at_1",
            "recall_at_10",
            "precision_at_1",
            "ndcg_at_10",
            "mrr",
            "latency_p50_ms",
            "latency_p95_ms",
            "latency_p99_ms",
        ]
        for key in expected_keys:
            assert key in result

    async def test_simulate_evaluation_contextualization_boost(self, runner):
        """Test contextualization improves recall and adds latency."""
        config_without = {"enable_contextualization": False}
        config_with = {"enable_contextualization": True}

        result_without = await runner._simulate_evaluation(config_without, [])
        result_with = await runner._simulate_evaluation(config_with, [])

        assert result_with["recall_at_1"] > result_without["recall_at_1"]
        assert result_with["latency_p95_ms"] > result_without["latency_p95_ms"]

    async def test_simulate_evaluation_small_chunks_penalty(self, runner):
        """Test small chunks reduce recall."""
        config_small = {"chunk_size": 400}
        config_large = {"chunk_size": 600}

        result_small = await runner._simulate_evaluation(config_small, [])
        result_large = await runner._simulate_evaluation(config_large, [])

        assert result_small["recall_at_1"] < result_large["recall_at_1"]


class TestCompareVariants:
    """Tests for _compare_variants method."""

    @pytest.fixture
    def runner(self):
        """Create runner with mocked logger."""
        with patch("src.evaluation.mlflow_experiments.MLflowRAGLogger") as mock_logger_class:
            mock_logger = MagicMock()
            mock_logger.tracking_uri = "http://localhost:5000"
            mock_logger_class.return_value = mock_logger
            yield RAGExperimentRunner(experiment_name="test")

    def test_compare_variants_winner_by_recall(self, runner):
        """Test variant with higher recall wins."""
        results_a = {"recall_at_1": 0.95, "ndcg_at_10": 0.90, "latency_p95_ms": 400}
        results_b = {"recall_at_1": 0.85, "ndcg_at_10": 0.92, "latency_p95_ms": 350}

        result = runner._compare_variants(
            test_name="test",
            variant_a_name="A",
            variant_b_name="B",
            results_a=results_a,
            results_b=results_b,
        )

        assert result["winner"] == "A"
        assert "Recall" in result["reason"]

    def test_compare_variants_winner_by_latency_on_tie(self, runner):
        """Test variant with lower latency wins when recall is tied."""
        results_a = {"recall_at_1": 0.90, "ndcg_at_10": 0.90, "latency_p95_ms": 400}
        results_b = {"recall_at_1": 0.905, "ndcg_at_10": 0.90, "latency_p95_ms": 350}

        result = runner._compare_variants(
            test_name="test",
            variant_a_name="A",
            variant_b_name="B",
            results_a=results_a,
            results_b=results_b,
        )

        # Within 0.01 is a tie, so latency decides
        assert result["winner"] == "B"
        assert "latency" in result["reason"]

    def test_compare_variants_calculates_delta(self, runner):
        """Test compare calculates metric deltas."""
        results_a = {"recall_at_1": 0.95, "ndcg_at_10": 0.90, "latency_p95_ms": 400}
        results_b = {"recall_at_1": 0.85, "ndcg_at_10": 0.85, "latency_p95_ms": 350}

        result = runner._compare_variants(
            test_name="test",
            variant_a_name="A",
            variant_b_name="B",
            results_a=results_a,
            results_b=results_b,
        )

        assert result["delta"]["recall_at_1"] == pytest.approx(0.10, abs=0.01)
        assert result["delta"]["ndcg_at_10"] == pytest.approx(0.05, abs=0.01)
        assert result["delta"]["latency_p95_ms"] == 50

    def test_compare_variants_returns_full_structure(self, runner):
        """Test compare returns complete comparison structure."""
        results_a = {"recall_at_1": 0.90, "ndcg_at_10": 0.90, "latency_p95_ms": 400}
        results_b = {"recall_at_1": 0.85, "ndcg_at_10": 0.90, "latency_p95_ms": 350}

        result = runner._compare_variants(
            test_name="my_test",
            variant_a_name="With Context",
            variant_b_name="No Context",
            results_a=results_a,
            results_b=results_b,
        )

        assert result["test_name"] == "my_test"
        assert result["variant_a"]["name"] == "With Context"
        assert result["variant_b"]["name"] == "No Context"
        assert result["variant_a"]["metrics"] == results_a
        assert result["variant_b"]["metrics"] == results_b

    def test_compare_variants_b_wins_when_higher_recall(self, runner):
        """Test variant B wins when it has higher recall."""
        results_a = {"recall_at_1": 0.80, "ndcg_at_10": 0.90, "latency_p95_ms": 300}
        results_b = {"recall_at_1": 0.95, "ndcg_at_10": 0.85, "latency_p95_ms": 500}

        result = runner._compare_variants(
            test_name="test",
            variant_a_name="A",
            variant_b_name="B",
            results_a=results_a,
            results_b=results_b,
        )

        assert result["winner"] == "B"
        assert "Recall" in result["reason"]

    def test_compare_variants_a_wins_latency_on_exact_tie(self, runner):
        """Test A wins on latency when recalls are exactly equal."""
        results_a = {"recall_at_1": 0.90, "ndcg_at_10": 0.90, "latency_p95_ms": 300}
        results_b = {"recall_at_1": 0.90, "ndcg_at_10": 0.90, "latency_p95_ms": 400}

        result = runner._compare_variants(
            test_name="test",
            variant_a_name="A",
            variant_b_name="B",
            results_a=results_a,
            results_b=results_b,
        )

        assert result["winner"] == "A"
        assert "latency" in result["reason"]
