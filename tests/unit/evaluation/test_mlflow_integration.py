# tests/unit/evaluation/test_mlflow_integration.py
"""Tests for MLflow integration."""

from unittest.mock import MagicMock, patch

import pytest


pytest.importorskip("mlflow", reason="mlflow not installed (eval extra)")
pytestmark = pytest.mark.requires_extras

from src.evaluation.mlflow_integration import MLflowRAGLogger, log_ab_test_results


class TestMLflowRAGLoggerInit:
    """Tests for MLflowRAGLogger initialization."""

    @patch("src.evaluation.mlflow_integration.mlflow")
    @patch("src.evaluation.mlflow_integration.MlflowClient")
    def test_init_creates_experiment(self, mock_client_class, mock_mlflow):
        """Test logger creates new experiment."""
        mock_client = MagicMock()
        mock_client.create_experiment.return_value = "exp-123"
        mock_client_class.return_value = mock_client

        logger = MLflowRAGLogger(experiment_name="test_exp")

        mock_mlflow.set_tracking_uri.assert_called_once_with("http://localhost:5000")
        mock_client.create_experiment.assert_called_once_with("test_exp")
        assert logger.experiment_id == "exp-123"

    @patch("src.evaluation.mlflow_integration.mlflow")
    @patch("src.evaluation.mlflow_integration.MlflowClient")
    def test_init_uses_existing_experiment(self, mock_client_class, mock_mlflow):
        """Test logger uses existing experiment when creation fails."""
        mock_client = MagicMock()
        mock_client.create_experiment.side_effect = Exception("Experiment already exists")
        mock_experiment = MagicMock()
        mock_experiment.experiment_id = "existing-123"
        mock_client.get_experiment_by_name.return_value = mock_experiment
        mock_client_class.return_value = mock_client

        logger = MLflowRAGLogger(experiment_name="existing")

        assert logger.experiment_id == "existing-123"
        mock_client.get_experiment_by_name.assert_called_once_with("existing")

    @patch("src.evaluation.mlflow_integration.mlflow")
    @patch("src.evaluation.mlflow_integration.MlflowClient")
    def test_init_sets_tracking_uri(self, mock_client_class, mock_mlflow):
        """Test logger sets custom tracking URI."""
        mock_client = MagicMock()
        mock_client.create_experiment.return_value = "exp-1"
        mock_client_class.return_value = mock_client

        logger = MLflowRAGLogger(tracking_uri="http://custom:5000")

        mock_mlflow.set_tracking_uri.assert_called_with("http://custom:5000")
        assert logger.tracking_uri == "http://custom:5000"

    @patch("src.evaluation.mlflow_integration.mlflow")
    @patch("src.evaluation.mlflow_integration.MlflowClient")
    def test_init_sets_experiment(self, mock_client_class, mock_mlflow):
        """Test logger calls mlflow.set_experiment."""
        mock_client = MagicMock()
        mock_client.create_experiment.return_value = "exp-1"
        mock_client_class.return_value = mock_client

        MLflowRAGLogger(experiment_name="my_experiment")

        mock_mlflow.set_experiment.assert_called_once_with("my_experiment")

    @patch("src.evaluation.mlflow_integration.mlflow")
    @patch("src.evaluation.mlflow_integration.MlflowClient")
    def test_init_default_values(self, mock_client_class, mock_mlflow):
        """Test logger uses default values."""
        mock_client = MagicMock()
        mock_client.create_experiment.return_value = "exp-1"
        mock_client_class.return_value = mock_client

        logger = MLflowRAGLogger()

        assert logger.experiment_name == "contextual_rag"
        assert logger.tracking_uri == "http://localhost:5000"
        assert logger.current_run is None


class TestRunManagement:
    """Tests for run management methods."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                yield log

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_start_run_creates_run(self, mock_mlflow, logger):
        """Test start_run creates MLflow run."""
        mock_run = MagicMock()
        mock_mlflow.start_run.return_value = mock_run

        result = logger.start_run(run_name="test_run")

        mock_mlflow.start_run.assert_called_once()
        assert logger.current_run == mock_run
        assert result == mock_run

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_start_run_adds_timestamp_tag(self, mock_mlflow, logger):
        """Test start_run adds timestamp tag."""
        logger.start_run(run_name="test", tags={"custom": "tag"})

        call_args = mock_mlflow.start_run.call_args
        tags = call_args[1]["tags"]
        assert "timestamp" in tags
        assert "custom" in tags
        assert tags["custom"] == "tag"

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_start_run_default_tags(self, mock_mlflow, logger):
        """Test start_run creates default tags dict if None."""
        logger.start_run(run_name="test")

        call_args = mock_mlflow.start_run.call_args
        tags = call_args[1]["tags"]
        assert "timestamp" in tags

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_start_run_passes_run_name(self, mock_mlflow, logger):
        """Test start_run passes run_name to mlflow."""
        logger.start_run(run_name="my_run")

        call_args = mock_mlflow.start_run.call_args
        assert call_args[1]["run_name"] == "my_run"

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_end_run_clears_current_run(self, mock_mlflow, logger):
        """Test end_run clears current run."""
        logger.current_run = MagicMock()

        logger.end_run()

        mock_mlflow.end_run.assert_called_once()
        assert logger.current_run is None

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_end_run_noop_when_no_run(self, mock_mlflow, logger):
        """Test end_run is safe when no current run."""
        logger.current_run = None

        logger.end_run()

        mock_mlflow.end_run.assert_not_called()


class TestLogConfig:
    """Tests for log_config method."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                yield log

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_returns_hash(self, mock_mlflow, logger):
        """Test log_config returns config hash."""
        config = {"key": "value", "num": 42}

        result = logger.log_config(config)

        assert len(result) == 12  # SHA256 hash truncated to 12 chars
        assert result.isalnum()

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_logs_parameters(self, mock_mlflow, logger):
        """Test log_config logs all parameters."""
        config = {"engine": "hybrid", "top_k": 10}

        logger.log_config(config, prefix="search.")

        mock_mlflow.log_param.assert_any_call("search.engine", "hybrid")
        mock_mlflow.log_param.assert_any_call("search.top_k", 10)

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_handles_nested_dict(self, mock_mlflow, logger):
        """Test log_config handles nested dictionaries."""
        config = {"outer": {"inner": "value"}}

        logger.log_config(config)

        mock_mlflow.log_param.assert_any_call("outer.inner", "value")

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_handles_list(self, mock_mlflow, logger):
        """Test log_config handles list values."""
        config = {"items": [1, 2, 3]}

        logger.log_config(config)

        # List should be JSON-encoded
        mock_mlflow.log_param.assert_any_call("items", "[1, 2, 3]")

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_handles_tuple(self, mock_mlflow, logger):
        """Test log_config handles tuple values."""
        config = {"coords": (1, 2)}

        logger.log_config(config)

        # Tuple should be JSON-encoded as list
        mock_mlflow.log_param.assert_any_call("coords", "[1, 2]")

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_same_input_same_hash(self, mock_mlflow, logger):
        """Test same config produces same hash."""
        config = {"a": 1, "b": 2}

        hash1 = logger.log_config(config)
        hash2 = logger.log_config(config)

        assert hash1 == hash2

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_no_prefix(self, mock_mlflow, logger):
        """Test log_config works without prefix."""
        config = {"key": "value"}

        logger.log_config(config)

        mock_mlflow.log_param.assert_any_call("key", "value")

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_config_deeply_nested(self, mock_mlflow, logger):
        """Test log_config handles deeply nested dictionaries."""
        config = {"level1": {"level2": {"level3": "deep_value"}}}

        logger.log_config(config)

        mock_mlflow.log_param.assert_any_call("level1.level2.level3", "deep_value")


class TestLogMetrics:
    """Tests for log_metrics method."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                yield log

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_metrics_from_dict(self, mock_mlflow, logger):
        """Test log_metrics logs dictionary of metrics."""
        metrics = {"precision": 0.94, "recall": 0.98}

        logger.log_metrics(metrics)

        mock_mlflow.log_metric.assert_any_call("precision", 0.94, step=None)
        mock_mlflow.log_metric.assert_any_call("recall", 0.98, step=None)

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_metrics_from_kwargs(self, mock_mlflow, logger):
        """Test log_metrics accepts kwargs."""
        logger.log_metrics(precision=0.94, recall=0.98)

        mock_mlflow.log_metric.assert_any_call("precision", 0.94, step=None)
        mock_mlflow.log_metric.assert_any_call("recall", 0.98, step=None)

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_metrics_with_step(self, mock_mlflow, logger):
        """Test log_metrics with step parameter."""
        logger.log_metrics({"loss": 0.5}, step=10)

        mock_mlflow.log_metric.assert_called_with("loss", 0.5, step=10)

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_metrics_merges_dict_and_kwargs(self, mock_mlflow, logger):
        """Test log_metrics merges dict and kwargs."""
        logger.log_metrics({"precision": 0.94}, recall=0.98)

        mock_mlflow.log_metric.assert_any_call("precision", 0.94, step=None)
        mock_mlflow.log_metric.assert_any_call("recall", 0.98, step=None)

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_metrics_empty(self, mock_mlflow, logger):
        """Test log_metrics handles empty metrics."""
        logger.log_metrics()

        mock_mlflow.log_metric.assert_not_called()


class TestLogArtifact:
    """Tests for artifact logging methods."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                yield log

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_artifact_file(self, mock_mlflow, logger):
        """Test log_artifact logs file."""
        logger.log_artifact("/path/to/file.json", artifact_path="data")

        mock_mlflow.log_artifact.assert_called_once_with("/path/to/file.json", artifact_path="data")

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_artifact_no_path(self, mock_mlflow, logger):
        """Test log_artifact without artifact_path."""
        logger.log_artifact("/path/to/file.json")

        mock_mlflow.log_artifact.assert_called_once_with("/path/to/file.json", artifact_path=None)

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_dict_artifact(self, mock_mlflow, logger):
        """Test log_dict_artifact creates temp file and logs."""
        data = {"key": "value"}

        logger.log_dict_artifact(data, "test.json", artifact_path="configs")

        mock_mlflow.log_artifact.assert_called_once()
        call_args = mock_mlflow.log_artifact.call_args
        assert call_args[1]["artifact_path"] == "configs"

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_dict_artifact_handles_permission_error(self, mock_mlflow, logger, capsys):
        """Test log_dict_artifact handles permission errors gracefully."""
        mock_mlflow.log_artifact.side_effect = PermissionError("Access denied")
        data = {"key": "value"}

        # Should not raise
        logger.log_dict_artifact(data, "test.json")

        captured = capsys.readouterr()
        assert "Warning" in captured.out

    @patch("src.evaluation.mlflow_integration.mlflow")
    def test_log_dict_artifact_no_artifact_path(self, mock_mlflow, logger):
        """Test log_dict_artifact without artifact_path."""
        data = {"key": "value"}

        logger.log_dict_artifact(data, "test.json")

        mock_mlflow.log_artifact.assert_called_once()


class TestLogQueryResults:
    """Tests for log_query_results method."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                yield log

    @patch.object(MLflowRAGLogger, "log_dict_artifact")
    def test_log_query_results_basic(self, mock_log_dict, logger):
        """Test log_query_results logs query data."""
        logger.log_query_results(
            query="test query",
            results=[{"doc": "1"}],
        )

        mock_log_dict.assert_called_once()
        call_args = mock_log_dict.call_args
        data = call_args[0][0]
        assert data["query"] == "test query"
        assert data["results_count"] == 1
        assert "timestamp" in data

    @patch.object(MLflowRAGLogger, "log_dict_artifact")
    def test_log_query_results_with_all_params(self, mock_log_dict, logger):
        """Test log_query_results with all optional params."""
        logger.log_query_results(
            query="статья 121 УК",
            results=[{"article": 121}],
            expected_article=121,
            precision_at_1=1.0,
            recall_at_10=1.0,
            latency_ms=420,
        )

        call_args = mock_log_dict.call_args
        data = call_args[0][0]
        assert data["expected_article"] == 121
        assert data["precision_at_1"] == 1.0
        assert data["recall_at_10"] == 1.0
        assert data["latency_ms"] == 420

    @patch.object(MLflowRAGLogger, "log_dict_artifact")
    def test_log_query_results_filename_format(self, mock_log_dict, logger):
        """Test log_query_results creates correct filename."""
        logger.log_query_results(
            query="test",
            results=[],
        )

        call_args = mock_log_dict.call_args
        filename = call_args[0][1]
        assert filename.startswith("query_")
        assert filename.endswith(".json")

    @patch.object(MLflowRAGLogger, "log_dict_artifact")
    def test_log_query_results_artifact_path(self, mock_log_dict, logger):
        """Test log_query_results uses correct artifact_path."""
        logger.log_query_results(query="test", results=[])

        call_args = mock_log_dict.call_args
        assert call_args[1]["artifact_path"] == "queries"

    @patch.object(MLflowRAGLogger, "log_dict_artifact")
    def test_log_query_results_empty_results(self, mock_log_dict, logger):
        """Test log_query_results handles empty results."""
        logger.log_query_results(query="test", results=[])

        call_args = mock_log_dict.call_args
        data = call_args[0][0]
        assert data["results_count"] == 0


class TestGetRunUrl:
    """Tests for get_run_url method."""

    @pytest.fixture
    def logger(self):
        with patch("src.evaluation.mlflow_integration.mlflow"):
            with patch("src.evaluation.mlflow_integration.MlflowClient") as mock_client:
                mock_client.return_value.create_experiment.return_value = "exp-1"
                log = MLflowRAGLogger()
                log.experiment_id = "exp-1"
                log.tracking_uri = "http://localhost:5000"
                yield log

    def test_get_run_url_no_current_run(self, logger):
        """Test get_run_url returns base URL when no run active."""
        logger.current_run = None

        url = logger.get_run_url()

        assert url == "http://localhost:5000"

    def test_get_run_url_with_current_run(self, logger):
        """Test get_run_url returns run-specific URL."""
        mock_run = MagicMock()
        mock_run.info.run_id = "run-123"
        logger.current_run = mock_run

        url = logger.get_run_url()

        assert "run-123" in url
        assert "exp-1" in url
        assert "http://localhost:5000" in url


class TestLogABTestResults:
    """Tests for log_ab_test_results convenience function."""

    @patch("src.evaluation.mlflow_integration.MLflowRAGLogger")
    @patch("src.evaluation.mlflow_integration.Path")
    def test_log_ab_test_results_full_flow(self, mock_path, mock_logger_class):
        """Test log_ab_test_results creates run and logs data."""
        mock_logger = MagicMock()
        mock_logger.start_run.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_logger.start_run.return_value.__exit__ = MagicMock(return_value=False)
        mock_logger.get_run_url.return_value = "http://mlflow/run/123"
        mock_logger_class.return_value = mock_logger
        mock_path.return_value.exists.return_value = True

        result = log_ab_test_results(
            engine_name="hybrid",
            config={"top_k": 10},
            metrics={"precision": 0.94},
            report_path="/path/to/report.md",
        )

        assert result == "http://mlflow/run/123"
        mock_logger.log_config.assert_called_once()
        mock_logger.log_metrics.assert_called_once()
        mock_logger.log_artifact.assert_called_once()

    @patch("src.evaluation.mlflow_integration.MLflowRAGLogger")
    @patch("src.evaluation.mlflow_integration.Path")
    def test_log_ab_test_results_no_report(self, mock_path, mock_logger_class):
        """Test log_ab_test_results skips artifact when report doesn't exist."""
        mock_logger = MagicMock()
        mock_logger.start_run.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_logger.start_run.return_value.__exit__ = MagicMock(return_value=False)
        mock_logger.get_run_url.return_value = "http://mlflow/run/123"
        mock_logger_class.return_value = mock_logger
        mock_path.return_value.exists.return_value = False

        log_ab_test_results(
            engine_name="hybrid",
            config={},
            metrics={},
            report_path="/nonexistent/report.md",
        )

        mock_logger.log_artifact.assert_not_called()

    @patch("src.evaluation.mlflow_integration.MLflowRAGLogger")
    @patch("src.evaluation.mlflow_integration.Path")
    def test_log_ab_test_results_custom_experiment(self, mock_path, mock_logger_class):
        """Test log_ab_test_results uses custom experiment name."""
        mock_logger = MagicMock()
        mock_logger.start_run.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_logger.start_run.return_value.__exit__ = MagicMock(return_value=False)
        mock_logger.get_run_url.return_value = "url"
        mock_logger_class.return_value = mock_logger
        mock_path.return_value.exists.return_value = False

        log_ab_test_results(
            engine_name="test",
            config={},
            metrics={},
            report_path="",
            experiment_name="custom_experiment",
        )

        mock_logger_class.assert_called_once_with(experiment_name="custom_experiment")

    @patch("src.evaluation.mlflow_integration.MLflowRAGLogger")
    @patch("src.evaluation.mlflow_integration.Path")
    def test_log_ab_test_results_run_name_format(self, mock_path, mock_logger_class):
        """Test log_ab_test_results creates run with correct name format."""
        mock_logger = MagicMock()
        mock_logger.start_run.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_logger.start_run.return_value.__exit__ = MagicMock(return_value=False)
        mock_logger.get_run_url.return_value = "url"
        mock_logger_class.return_value = mock_logger
        mock_path.return_value.exists.return_value = False

        log_ab_test_results(
            engine_name="dbsf_colbert",
            config={},
            metrics={},
            report_path="",
        )

        call_args = mock_logger.start_run.call_args
        run_name = call_args[1]["run_name"]
        assert run_name.startswith("dbsf_colbert_")
        tags = call_args[1]["tags"]
        assert tags["engine"] == "dbsf_colbert"

    @patch("src.evaluation.mlflow_integration.MLflowRAGLogger")
    @patch("src.evaluation.mlflow_integration.Path")
    def test_log_ab_test_results_config_prefix(self, mock_path, mock_logger_class):
        """Test log_ab_test_results logs config with search_engine prefix."""
        mock_logger = MagicMock()
        mock_logger.start_run.return_value.__enter__ = MagicMock(return_value=MagicMock())
        mock_logger.start_run.return_value.__exit__ = MagicMock(return_value=False)
        mock_logger.get_run_url.return_value = "url"
        mock_logger_class.return_value = mock_logger
        mock_path.return_value.exists.return_value = False

        log_ab_test_results(
            engine_name="test",
            config={"top_k": 10},
            metrics={},
            report_path="",
        )

        mock_logger.log_config.assert_called_once_with({"top_k": 10}, prefix="search_engine.")
