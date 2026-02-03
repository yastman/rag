#!/usr/bin/env python3
"""
MLflow Integration for Contextual RAG

Replaces config_snapshot.py with production-grade experiment tracking.

Features:
    - Automatic experiment creation and run management
    - Config versioning via MLflow parameters
    - Metrics logging (precision, recall, latency)
    - Artifact storage (reports, query results, configs)
    - Model registry integration

Usage:
    from mlflow_integration import MLflowRAGLogger

    logger = MLflowRAGLogger(experiment_name="contextual_rag")

    with logger.start_run(run_name="dbsf_colbert_v2.0.1"):
        logger.log_config(search_engine_config)
        logger.log_metrics(precision=0.94, recall=0.98, latency_p95=420)
        logger.log_artifact("reports/AB_TEST_REPORT.md")

Integration with monitoring:
    - MLflow UI: http://localhost:5000
    - Prometheus metrics: /metrics endpoint
    - Grafana dashboards: MLflow tracking

Environment:
    MLFLOW_TRACKING_URI: http://localhost:5000 (from docker-compose)
"""

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import mlflow
from mlflow.tracking import MlflowClient


class MLflowRAGLogger:
    """
    MLflow integration for RAG experiment tracking.

    Replaces config_snapshot.py with production-grade tracking.

    Attributes:
        experiment_name: MLflow experiment name
        client: MLflow tracking client
        current_run: Active MLflow run
    """

    def __init__(
        self,
        experiment_name: str = "contextual_rag",
        tracking_uri: str = "http://localhost:5000",
    ):
        """
        Initialize MLflow logger.

        Args:
            experiment_name: Experiment name for grouping runs
            tracking_uri: MLflow tracking server URL
        """
        self.experiment_name = experiment_name
        self.tracking_uri = tracking_uri

        # Set tracking URI
        mlflow.set_tracking_uri(tracking_uri)

        # Create or get experiment
        self.client = MlflowClient(tracking_uri=tracking_uri)
        try:
            self.experiment_id = self.client.create_experiment(experiment_name)
        except Exception:
            # Experiment already exists
            experiment = self.client.get_experiment_by_name(experiment_name)
            self.experiment_id = experiment.experiment_id

        mlflow.set_experiment(experiment_name)

        self.current_run = None

    def start_run(self, run_name: str | None = None, tags: dict[str, Any] | None = None):
        """
        Start a new MLflow run (context manager).

        Args:
            run_name: Human-readable run name
            tags: Additional tags for the run

        Returns:
            Context manager for MLflow run

        Example:
            with logger.start_run(run_name="baseline_eval"):
                logger.log_metrics(precision=0.91)
        """
        if tags is None:
            tags = {}

        # Add timestamp tag
        tags["timestamp"] = datetime.now().isoformat()

        self.current_run = mlflow.start_run(run_name=run_name, tags=tags)
        return self.current_run

    def log_config(
        self,
        config: dict[str, Any],
        prefix: str = "",
    ) -> str:
        """
        Log configuration parameters and compute hash.

        Replaces get_config_hash() from config_snapshot.py.

        Args:
            config: Configuration dictionary
            prefix: Prefix for parameter names (e.g., "search_engine.")

        Returns:
            Config hash (12-char SHA256)

        Example:
            config_hash = logger.log_config({
                "engine": "dbsf_colbert",
                "embedding_model": "bge-m3",
                "top_k": 10,
            })
        """
        # Compute config hash
        config_json = json.dumps(config, sort_keys=True)
        config_hash = hashlib.sha256(config_json.encode()).hexdigest()[:12]

        # Log config hash as parameter
        mlflow.log_param(f"{prefix}config_hash", config_hash)

        # Log individual config values
        self._log_nested_params(config, prefix)

        return config_hash

    def _log_nested_params(self, params: dict[str, Any], prefix: str = ""):
        """
        Recursively log nested config parameters.

        Args:
            params: Parameter dictionary (possibly nested)
            prefix: Prefix for parameter names
        """
        for key, value in params.items():
            param_name = f"{prefix}{key}" if prefix else key

            if isinstance(value, dict):
                # Recurse into nested dict
                self._log_nested_params(value, f"{param_name}.")
            elif isinstance(value, (list, tuple)):
                # Log list as JSON string
                mlflow.log_param(param_name, json.dumps(value))
            else:
                # Log primitive value
                mlflow.log_param(param_name, value)

    def log_metrics(
        self,
        metrics: dict[str, float] | None = None,
        step: int | None = None,
        **kwargs,
    ) -> None:
        """
        Log evaluation metrics.

        Args:
            metrics: Dictionary of metric name -> value
            step: Optional step number for time series
            **kwargs: Additional metrics as keyword arguments

        Example:
            logger.log_metrics({
                "precision_at_1": 0.94,
                "recall_at_10": 0.98,
                "latency_p50_ms": 350,
                "latency_p95_ms": 420,
            })

            # Or use kwargs:
            logger.log_metrics(precision_at_1=0.94, recall_at_10=0.98)
        """
        if metrics is None:
            metrics = {}

        # Merge kwargs into metrics
        metrics.update(kwargs)

        # Log each metric
        for name, value in metrics.items():
            mlflow.log_metric(name, value, step=step)

    def log_artifact(
        self,
        local_path: str | Path,
        artifact_path: str | None = None,
    ) -> None:
        """
        Log file artifact (report, config file, etc.).

        Args:
            local_path: Path to local file
            artifact_path: Subdirectory in MLflow artifacts

        Example:
            logger.log_artifact("reports/AB_TEST_REPORT.md", artifact_path="reports")
            logger.log_artifact("config_snapshot.json", artifact_path="configs")
        """
        mlflow.log_artifact(str(local_path), artifact_path=artifact_path)

    def log_dict_artifact(
        self,
        data: dict[str, Any],
        filename: str,
        artifact_path: str | None = None,
    ) -> None:
        """
        Log dictionary as JSON artifact.

        Args:
            data: Dictionary to log
            filename: Filename for the artifact
            artifact_path: Subdirectory in MLflow artifacts

        Example:
            logger.log_dict_artifact(
                {"engine": "dbsf_colbert", "results": [...]},
                "search_results.json",
                artifact_path="data"
            )
        """
        import tempfile

        # Create temporary file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f, indent=2)
            temp_path = f.name

        try:
            # Log the file as artifact
            mlflow.log_artifact(temp_path, artifact_path=artifact_path)
        except PermissionError as e:
            # Handle case where artifact storage is not accessible (e.g., Docker container)
            print(f"⚠️  Warning: Could not log artifact (permission issue): {e}")
            print("   Metrics and parameters logged successfully to MLflow UI")
        finally:
            # Clean up temporary file
            if Path(temp_path).exists():
                Path(temp_path).unlink()

    def log_query_results(
        self,
        query: str,
        results: list[dict[str, Any]],
        expected_article: int | None = None,
        precision_at_1: float | None = None,
        recall_at_10: float | None = None,
        latency_ms: float | None = None,
    ) -> None:
        """
        Log individual query evaluation results.

        Args:
            query: Search query text
            results: List of retrieved documents
            expected_article: Expected article number (ground truth)
            precision_at_1: Precision at rank 1
            recall_at_10: Recall at rank 10
            latency_ms: Query latency in milliseconds

        Example:
            logger.log_query_results(
                query="статья 121 УК",
                results=search_results,
                expected_article=121,
                precision_at_1=1.0,
                recall_at_10=1.0,
                latency_ms=420
            )
        """
        query_data = {
            "query": query,
            "timestamp": time.time(),
            "results_count": len(results),
        }

        if expected_article is not None:
            query_data["expected_article"] = expected_article

        if precision_at_1 is not None:
            query_data["precision_at_1"] = precision_at_1

        if recall_at_10 is not None:
            query_data["recall_at_10"] = recall_at_10

        if latency_ms is not None:
            query_data["latency_ms"] = latency_ms

        # Log as artifact
        query_id = hashlib.md5(query.encode()).hexdigest()[:8]
        self.log_dict_artifact(query_data, f"query_{query_id}.json", artifact_path="queries")

    def end_run(self) -> None:
        """End the current MLflow run."""
        if self.current_run:
            mlflow.end_run()
            self.current_run = None

    def get_run_url(self) -> str:
        """
        Get URL for current run in MLflow UI.

        Returns:
            URL to view run in MLflow UI
        """
        if not self.current_run:
            return f"{self.tracking_uri}"

        run_id = self.current_run.info.run_id
        return f"{self.tracking_uri}/#/experiments/{self.experiment_id}/runs/{run_id}"


# Convenience function for quick logging
def log_ab_test_results(
    engine_name: str,
    config: dict[str, Any],
    metrics: dict[str, float],
    report_path: str | Path,
    experiment_name: str = "contextual_rag_ab_tests",
) -> str:
    """
    Quick helper to log A/B test results.

    Args:
        engine_name: Search engine name (baseline, dbsf_colbert, etc.)
        config: Search engine configuration
        metrics: Evaluation metrics
        report_path: Path to markdown report
        experiment_name: MLflow experiment name

    Returns:
        MLflow run URL

    Example:
        run_url = log_ab_test_results(
            engine_name="dbsf_colbert",
            config={"embedding": "bge-m3", "top_k": 10},
            metrics={"precision_at_1": 0.94, "recall_at_10": 0.98},
            report_path="reports/AB_TEST_REPORT_20251023.md"
        )
        print(f"View results: {run_url}")
    """
    logger = MLflowRAGLogger(experiment_name=experiment_name)

    run_name = f"{engine_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    with logger.start_run(run_name=run_name, tags={"engine": engine_name}):
        # Log config
        logger.log_config(config, prefix="search_engine.")

        # Log metrics
        logger.log_metrics(metrics)

        # Log report
        if Path(report_path).exists():
            logger.log_artifact(report_path, artifact_path="reports")

        return logger.get_run_url()


if __name__ == "__main__":
    # Example usage
    print("=" * 80)
    print("MLFLOW INTEGRATION - Example Usage")
    print("=" * 80)

    logger = MLflowRAGLogger(experiment_name="contextual_rag_example")

    print(f"\n📊 MLflow UI: {logger.tracking_uri}")
    print(f"📁 Experiment: {logger.experiment_name}")

    # Example run
    print("\n🏃 Starting example run...")
    with logger.start_run(run_name="dbsf_colbert_example", tags={"test": "true"}):
        # Log config
        config = {
            "engine": "dbsf_colbert",
            "embedding_model": "bge-m3",
            "embedding_dim": 1024,
            "top_k": 10,
            "score_threshold": 0.3,
        }
        config_hash = logger.log_config(config, prefix="search_engine.")
        print(f"   Config hash: {config_hash}")

        # Log metrics
        metrics = {
            "precision_at_1": 0.94,
            "recall_at_10": 0.98,
            "latency_p50_ms": 350,
            "latency_p95_ms": 420,
        }
        logger.log_metrics(metrics)
        print(f"   Logged {len(metrics)} metrics")

        # Log query results
        logger.log_query_results(
            query="статья 121 УК",
            results=[{"article": 121, "score": 0.95}],
            expected_article=121,
            precision_at_1=1.0,
            recall_at_10=1.0,
            latency_ms=420,
        )
        print("   Logged query results")

        run_url = logger.get_run_url()

    print(f"\n✅ Run complete! View results: {run_url}")
    print("=" * 80)
