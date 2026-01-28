"""CLI for baseline operations."""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click

from .collector import LangfuseMetricsCollector
from .manager import BaselineManager


def get_collector() -> LangfuseMetricsCollector:
    """Create collector from environment."""
    return LangfuseMetricsCollector(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-dev"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-dev"),
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
    )


@click.group()
def cli():
    """Baseline management CLI."""


@cli.command()
@click.option("--baseline", required=True, help="Baseline session tag")
@click.option("--current", required=True, help="Current session tag")
@click.option(
    "--thresholds",
    default="tests/baseline/thresholds.yaml",
    help="Path to thresholds file",
)
@click.option("--hours", default=24, help="Hours to look back for metrics")
def compare(baseline: str, current: str, thresholds: str, hours: int):
    """Compare current run against baseline."""
    collector = get_collector()
    manager = BaselineManager(
        collector=collector,
        thresholds_path=Path(thresholds),
    )

    # Time range
    now = datetime.now(UTC)
    from_ts = now - timedelta(hours=hours)

    click.echo(f"Fetching baseline metrics: {baseline}")
    baseline_snapshot = manager.create_snapshot(
        tag=baseline,
        session_id=baseline,
        from_ts=from_ts,
        to_ts=now,
    )

    click.echo(f"Fetching current metrics: {current}")
    current_snapshot = manager.create_snapshot(
        tag=current,
        session_id=current,
        from_ts=from_ts,
        to_ts=now,
    )

    click.echo("\nComparing metrics...")
    passed, regressions = manager.compare(current_snapshot, baseline_snapshot)

    click.echo("\n" + "=" * 60)
    click.echo("BASELINE COMPARISON RESULTS")
    click.echo("=" * 60)

    # Print metrics table
    click.echo(f"\n{'Metric':<30} {'Baseline':<15} {'Current':<15} {'Change':<10}")
    click.echo("-" * 70)

    def fmt_change(curr, base):
        if base == 0:
            return "N/A"
        pct = (curr / base - 1) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    click.echo(
        f"{'LLM p95 latency (ms)':<30} "
        f"{baseline_snapshot.llm_latency_p95_ms:<15.0f} "
        f"{current_snapshot.llm_latency_p95_ms:<15.0f} "
        f"{fmt_change(current_snapshot.llm_latency_p95_ms, baseline_snapshot.llm_latency_p95_ms):<10}"
    )
    click.echo(
        f"{'Total cost (USD)':<30} "
        f"{baseline_snapshot.total_cost_usd:<15.4f} "
        f"{current_snapshot.total_cost_usd:<15.4f} "
        f"{fmt_change(current_snapshot.total_cost_usd, baseline_snapshot.total_cost_usd):<10}"
    )
    click.echo(
        f"{'Cache hit rate':<30} "
        f"{baseline_snapshot.cache_hit_rate:<15.1%} "
        f"{current_snapshot.cache_hit_rate:<15.1%} "
        f"{fmt_change(current_snapshot.cache_hit_rate, baseline_snapshot.cache_hit_rate):<10}"
    )
    click.echo(
        f"{'LLM calls':<30} "
        f"{baseline_snapshot.llm_calls:<15} "
        f"{current_snapshot.llm_calls:<15} "
        f"{fmt_change(current_snapshot.llm_calls, baseline_snapshot.llm_calls):<10}"
    )

    click.echo("\n" + "=" * 60)

    if passed:
        click.secho("PASSED - No regressions detected", fg="green", bold=True)
        sys.exit(0)
    else:
        click.secho("FAILED - Regressions detected:", fg="red", bold=True)
        for regression in regressions:
            click.echo(f"  - {regression}")
        sys.exit(1)


@cli.command("set-baseline")
@click.option("--tag", required=True, help="Tag to set as baseline")
def set_baseline(tag: str):
    """Set a run as the new baseline."""
    # For now, just record to a file
    baseline_file = Path("tests/baseline/.current_baseline")
    baseline_file.write_text(tag)
    click.echo(f"Baseline set to: {tag}")


@cli.command()
@click.option("--output", default="reports/baseline.html", help="Output file path")
def report(output: str):
    """Generate HTML baseline report."""
    click.echo(f"Generating report to {output}...")
    # TODO: Implement HTML report generation
    click.echo("Report generation not yet implemented")


if __name__ == "__main__":
    cli()
