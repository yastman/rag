"""Unit tests for src/evaluation/metrics_logger.py."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch


class TestQueryMetrics:
    """Test QueryMetrics dataclass."""

    def test_query_metrics_creation(self):
        """Test QueryMetrics creation with all fields."""
        from src.evaluation.metrics_logger import QueryMetrics

        with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc123"):
            metrics = QueryMetrics(
                query_id="test_1",
                engine="hybrid",
                latency_ms=450.0,
                precision_at_1=1.0,
                recall_at_10=1.0,
                num_results=10,
                config_hash="abc123",
            )

            assert metrics.query_id == "test_1"
            assert metrics.engine == "hybrid"
            assert metrics.latency_ms == 450.0
            assert metrics.precision_at_1 == 1.0
            assert metrics.user_id == "anonymous"

    def test_query_metrics_to_dict(self):
        """Test QueryMetrics serialization to dict."""
        from src.evaluation.metrics_logger import QueryMetrics

        metrics = QueryMetrics(
            query_id="test_1",
            engine="hybrid",
            latency_ms=450.0,
            precision_at_1=1.0,
            recall_at_10=1.0,
            num_results=10,
            config_hash="abc123",
        )

        data = metrics.to_dict()

        assert data["query_id"] == "test_1"
        assert data["engine"] == "hybrid"
        assert "timestamp" in data

    def test_query_metrics_to_json(self):
        """Test QueryMetrics serialization to JSON."""
        from src.evaluation.metrics_logger import QueryMetrics

        metrics = QueryMetrics(
            query_id="test_1",
            engine="hybrid",
            latency_ms=450.0,
            precision_at_1=1.0,
            recall_at_10=1.0,
            num_results=10,
            config_hash="abc123",
        )

        json_str = metrics.to_json()
        parsed = json.loads(json_str)

        assert parsed["query_id"] == "test_1"

    def test_query_metrics_to_prometheus(self):
        """Test QueryMetrics Prometheus format export."""
        from src.evaluation.metrics_logger import QueryMetrics

        metrics = QueryMetrics(
            query_id="test_1",
            engine="hybrid",
            latency_ms=450.0,
            precision_at_1=1.0,
            recall_at_10=1.0,
            num_results=10,
            config_hash="abc123",
        )

        prom_str = metrics.to_prometheus()

        assert "rag_query_latency_ms" in prom_str
        assert 'engine="hybrid"' in prom_str
        assert "450.0" in prom_str


class TestMetricsLogger:
    """Test MetricsLogger class."""

    def test_logger_init_creates_directory(self):
        """Test that logger creates log directory on init."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            log_dir = Path(tmpdir) / "logs"

            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                MetricsLogger(log_dir=str(log_dir))

            assert log_dir.exists()

    def test_logger_log_query(self):
        """Test logging a query."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)

                metrics = logger.log_query(
                    query="test query",
                    engine="hybrid",
                    latency_ms=450.0,
                    precision_at_1=1.0,
                )

                assert metrics.engine == "hybrid"
                assert metrics.latency_ms == 450.0
                assert len(logger.metrics_buffer) == 1

    def test_logger_aggregates_stats(self):
        """Test that logger aggregates statistics by engine."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)

                # Log multiple queries
                logger.log_query("q1", "hybrid", 400.0, 1.0)
                logger.log_query("q2", "hybrid", 500.0, 1.0)
                logger.log_query("q3", "baseline", 300.0, 0.0)

                assert len(logger.aggregated_stats["hybrid"]["latency_ms"]) == 2
                assert len(logger.aggregated_stats["baseline"]["latency_ms"]) == 1

    def test_logger_writes_json_log(self):
        """Test that logger writes JSON log files."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)

                logger.log_query("q1", "hybrid", 400.0, 1.0)

                # Check that a log file was created
                log_files = list(Path(tmpdir).glob("metrics_*.jsonl"))
                assert len(log_files) == 1

                # Verify content
                content = log_files[0].read_text()
                assert "hybrid" in content

    def test_logger_export_prometheus(self):
        """Test Prometheus metrics export."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)

                logger.log_query("q1", "hybrid", 400.0, 1.0)
                logger.log_query("q2", "hybrid", 500.0, 1.0)

                prom_export = logger.export_prometheus()

                assert "rag_queries_total" in prom_export
                assert "rag_latency_ms" in prom_export
                assert "hybrid" in prom_export

    def test_logger_get_summary(self):
        """Test summary statistics."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)

                # Log 10 queries for percentile calculation
                for i in range(10):
                    logger.log_query(f"q{i}", "hybrid", 400.0 + i * 10, 1.0)

                summary = logger.get_summary()

                assert "hybrid" in summary
                assert summary["hybrid"]["total_queries"] == 10
                assert "latency_p50_ms" in summary["hybrid"]
                assert "precision_at_1" in summary["hybrid"]


class TestSLOTracking:
    """Test SLO (Service Level Objective) tracking."""

    def test_slo_thresholds_defaults(self):
        """Test default SLO threshold values."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)

                assert logger.slo_thresholds["p50_latency_ms"] == 400
                assert logger.slo_thresholds["p95_latency_ms"] == 800
                assert logger.slo_thresholds["precision_at_1_min"] == 0.90

    def test_slo_violation_count(self):
        """Test SLO violation counting."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)

                # Log queries with poor latency
                for i in range(10):
                    logger.log_query(f"q{i}", "slow_engine", 2000.0, 1.0)  # Very slow

                violations = logger._count_slo_violations("slow_engine")

                assert violations >= 1  # At least latency SLO violated


class TestAnomalyDetection:
    """Test anomaly detection functionality."""

    def test_latency_anomaly_logged(self):
        """Test that latency anomalies are logged."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)

                # Log query with anomalous latency (> p99 threshold)
                logger.log_query("q1", "hybrid", 5000.0, 1.0)

                # Check anomaly log exists
                anomaly_log = Path(tmpdir) / "anomalies.log"
                assert anomaly_log.exists()
                assert "LATENCY ANOMALY" in anomaly_log.read_text()

    def test_quality_anomaly_logged(self):
        """Test that quality anomalies are logged."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)
                # Override threshold to trigger anomaly
                logger.slo_thresholds["precision_at_1_min"] = 1.0

                # Log query with low precision
                logger.log_query("q1", "hybrid", 400.0, 0.5)

                # Check anomaly log exists
                anomaly_log = Path(tmpdir) / "anomalies.log"
                assert anomaly_log.exists()
                assert "QUALITY ANOMALY" in anomaly_log.read_text()

    def test_zero_results_anomaly(self):
        """Test that zero results are logged as anomaly."""
        from src.evaluation.metrics_logger import MetricsLogger

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("src.evaluation.config_snapshot.get_config_hash", return_value="abc"):
                logger = MetricsLogger(log_dir=tmpdir)

                # Log query with zero results
                logger.log_query("q1", "hybrid", 400.0, 0.0, num_results=0)

                # Check anomaly log
                anomaly_log = Path(tmpdir) / "anomalies.log"
                assert anomaly_log.exists()
                assert "ZERO RESULTS" in anomaly_log.read_text()
