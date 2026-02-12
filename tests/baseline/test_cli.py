"""Tests for baseline CLI."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from tests.baseline.cli import cli, compare, set_baseline


class TestCompareBootstrap:
    """Tests for bootstrap SKIP when no baseline exists."""

    @patch("tests.baseline.cli.get_collector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_skip_when_no_baseline_traces(self, mock_manager_cls, mock_get_collector):
        """Should exit 0 with SKIP when no baseline traces found."""
        mock_collector = MagicMock()
        mock_get_collector.return_value = mock_collector

        mock_manager = MagicMock()
        mock_manager.collector = mock_collector
        mock_collector.collect_session_metrics.return_value = MagicMock(trace_count=0)
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--baseline-tag=main-latest",
                    "--current-session=ci-abc-job-1",
                    "--output=report.json",
                ],
            )

        assert result.exit_code == 0
        assert "SKIP" in result.output.upper() or "skip" in result.output.lower()

    @patch("tests.baseline.cli.get_collector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_skip_writes_structured_json(self, mock_manager_cls, mock_get_collector):
        """Should write structured JSON with skip reason."""
        mock_collector = MagicMock()
        mock_get_collector.return_value = mock_collector

        mock_manager = MagicMock()
        mock_manager.collector = mock_collector
        mock_collector.collect_session_metrics.return_value = MagicMock(trace_count=0)
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--baseline-tag=main-latest",
                    "--current-session=ci-abc-job-1",
                    "--output=report.json",
                ],
            )

            assert result.exit_code == 0
            report = json.loads(Path("report.json").read_text())
            assert report["status"] == "skipped"
            assert "reason" in report


class TestCompareNewFlags:
    """Tests for new CLI flags."""

    @patch("tests.baseline.cli.get_collector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_compare_with_new_flags_passes(self, mock_manager_cls, mock_get_collector):
        """Should pass with --baseline-tag and --current-session."""
        mock_collector = MagicMock()
        mock_get_collector.return_value = mock_collector

        baseline_metrics = MagicMock(
            trace_count=5,
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            total_cost_usd=0.05,
            cache_hit_rate=0.65,
            llm_calls=100,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            cache_hits=65,
            cache_misses=35,
        )
        current_metrics = MagicMock(
            trace_count=5,
            llm_latency_p50_ms=160.0,
            llm_latency_p95_ms=360.0,
            total_cost_usd=0.052,
            cache_hit_rate=0.63,
            llm_calls=102,
            llm_tokens_input=10200,
            llm_tokens_output=2550,
            cache_hits=63,
            cache_misses=37,
        )
        mock_collector.collect_session_metrics.side_effect = [baseline_metrics, current_metrics]

        mock_manager = MagicMock()
        mock_manager.collector = mock_collector
        mock_manager.compare.return_value = (True, [])
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--baseline-tag=main-latest",
                    "--current-session=ci-abc-job-1",
                    "--output=report.json",
                ],
            )

            assert result.exit_code == 0
            assert "PASSED" in result.output
            report = json.loads(Path("report.json").read_text())
            assert report["status"] == "passed"

    @patch("tests.baseline.cli.get_collector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_compare_writes_failed_json(self, mock_manager_cls, mock_get_collector):
        """Should write status=failed JSON on regression."""
        mock_collector = MagicMock()
        mock_get_collector.return_value = mock_collector

        metrics = MagicMock(
            trace_count=5,
            llm_latency_p50_ms=150.0,
            llm_latency_p95_ms=350.0,
            total_cost_usd=0.05,
            cache_hit_rate=0.65,
            llm_calls=100,
            llm_tokens_input=10000,
            llm_tokens_output=2500,
            cache_hits=65,
            cache_misses=35,
        )
        mock_collector.collect_session_metrics.return_value = metrics

        mock_manager = MagicMock()
        mock_manager.collector = mock_collector
        mock_manager.compare.return_value = (False, ["LLM p95 latency regression"])
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(
                cli,
                [
                    "compare",
                    "--baseline-tag=main-latest",
                    "--current-session=ci-abc-job-1",
                    "--output=report.json",
                ],
            )

            assert result.exit_code == 1
            report = json.loads(Path("report.json").read_text())
            assert report["status"] == "failed"
            assert len(report["regressions"]) == 1


class TestSetBaselineNew:
    """Tests for tag-based set-baseline command."""

    def test_set_baseline_help_shows_new_flags(self):
        """set-baseline should show --session-id and --tag flags."""
        runner = CliRunner()
        result = runner.invoke(set_baseline, ["--help"])
        assert result.exit_code == 0
        assert "--session-id" in result.output
        assert "--tag" in result.output

    def test_set_baseline_requires_tag(self):
        """set-baseline command should require --tag."""
        runner = CliRunner()
        result = runner.invoke(set_baseline, ["--session-id=abc"])
        assert result.exit_code != 0

    def test_set_baseline_requires_session_id(self):
        """set-baseline command should require --session-id."""
        runner = CliRunner()
        result = runner.invoke(set_baseline, ["--tag=main-latest"])
        assert result.exit_code != 0


class TestCLIHelp:
    """Tests for CLI help output."""

    def test_cli_help(self):
        """CLI should show help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "baseline" in result.output.lower()

    def test_compare_help(self):
        """compare command should show new flags."""
        runner = CliRunner()
        result = runner.invoke(compare, ["--help"])
        assert result.exit_code == 0
        assert "--baseline-tag" in result.output
        assert "--current-session" in result.output
        assert "--output" in result.output
