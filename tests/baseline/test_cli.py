"""Tests for baseline CLI."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from tests.baseline.cli import cli, compare, set_baseline


class TestBaselineCLI:
    """Test baseline CLI commands."""

    def test_compare_requires_baseline_tag(self):
        """compare command should require --baseline."""
        runner = CliRunner()
        result = runner.invoke(compare, ["--current=abc"])
        assert result.exit_code != 0
        assert "baseline" in result.output.lower() or "missing" in result.output.lower()

    def test_compare_requires_current_tag(self):
        """compare command should require --current."""
        runner = CliRunner()
        result = runner.invoke(compare, ["--baseline=abc"])
        assert result.exit_code != 0

    @patch("tests.baseline.cli.LangfuseMetricsCollector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_compare_outputs_results(self, mock_manager_cls, mock_collector_cls):
        """compare should output comparison results."""
        mock_manager = MagicMock()
        mock_manager.compare.return_value = (True, [])
        mock_manager.create_snapshot.return_value = MagicMock(
            llm_latency_p95_ms=350.0,
            total_cost_usd=0.05,
            cache_hit_rate=0.65,
            llm_calls=100,
        )
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        result = runner.invoke(
            compare,
            [
                "--baseline=smoke-abc-20260128",
                "--current=smoke-def-20260128",
            ],
        )

        # Should not error
        assert result.exit_code == 0

    @patch("tests.baseline.cli.LangfuseMetricsCollector")
    @patch("tests.baseline.cli.BaselineManager")
    def test_compare_fails_on_regression(self, mock_manager_cls, mock_collector_cls):
        """compare should exit 1 on regressions."""
        mock_manager = MagicMock()
        mock_manager.compare.return_value = (False, ["LLM latency regression"])
        mock_manager.create_snapshot.return_value = MagicMock(
            llm_latency_p95_ms=350.0,
            total_cost_usd=0.05,
            cache_hit_rate=0.65,
            llm_calls=100,
        )
        mock_manager_cls.return_value = mock_manager

        runner = CliRunner()
        result = runner.invoke(
            compare,
            [
                "--baseline=smoke-abc-20260128",
                "--current=smoke-def-20260128",
            ],
        )

        assert result.exit_code == 1
        assert "regression" in result.output.lower()

    def test_set_baseline_requires_tag(self):
        """set-baseline command should require --tag."""
        runner = CliRunner()
        result = runner.invoke(set_baseline, [])
        assert result.exit_code != 0

    def test_set_baseline_writes_file(self, tmp_path):
        """set-baseline should write tag to file."""
        runner = CliRunner()
        with runner.isolated_filesystem(temp_dir=tmp_path):
            # Create tests/baseline directory
            import os

            os.makedirs("tests/baseline", exist_ok=True)

            result = runner.invoke(set_baseline, ["--tag=smoke-test-123"])

            assert result.exit_code == 0
            assert "smoke-test-123" in result.output

    def test_cli_help(self):
        """CLI should show help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "baseline" in result.output.lower()

    def test_compare_help(self):
        """compare command should show help."""
        runner = CliRunner()
        result = runner.invoke(compare, ["--help"])
        assert result.exit_code == 0
        assert "--baseline" in result.output
        assert "--current" in result.output
