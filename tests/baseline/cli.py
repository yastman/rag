"""CLI for baseline operations."""

import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click

from scripts.validate_traces import check_worktree_clean

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
    check_worktree_clean(strict=False)
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
@click.option("--baseline", required=False, help="Baseline session tag")
@click.option("--current", required=False, help="Current session tag")
@click.option(
    "--thresholds",
    default="tests/baseline/thresholds.yaml",
    help="Path to thresholds file",
)
@click.option("--hours", default=24, help="Hours to look back for metrics")
@click.option("--output", default="reports/baseline.html", help="Output file path")
def report(baseline: str | None, current: str | None, thresholds: str, hours: int, output: str):
    """Generate HTML baseline report."""
    baseline = baseline or os.getenv("BASELINE_TAG")
    current = current or os.getenv("CURRENT_TAG")

    baseline_file = Path("tests/baseline/.current_baseline")
    if baseline is None and baseline_file.exists():
        baseline = baseline_file.read_text().strip()

    if not baseline or not current:
        click.secho(
            "BASELINE_TAG and CURRENT_TAG are required (or pass --baseline/--current).",
            fg="red",
        )
        sys.exit(1)

    click.echo(f"Generating report to {output}...")
    collector = get_collector()
    manager = BaselineManager(
        collector=collector,
        thresholds_path=Path(thresholds),
    )

    now = datetime.now(UTC)
    from_ts = now - timedelta(hours=hours)

    baseline_snapshot = manager.create_snapshot(
        tag=baseline,
        session_id=baseline,
        from_ts=from_ts,
        to_ts=now,
    )
    current_snapshot = manager.create_snapshot(
        tag=current,
        session_id=current,
        from_ts=from_ts,
        to_ts=now,
    )

    passed, regressions = manager.compare(current_snapshot, baseline_snapshot)

    report_path = Path(output)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    def fmt_pct(curr: float, base: float) -> str:
        if base == 0:
            return "N/A"
        pct = (curr / base - 1) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Baseline Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; color: #222; }}
    h1 {{ margin-bottom: 8px; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 16px; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f3f3f3; }}
    .pass {{ color: #0a7d2c; font-weight: bold; }}
    .fail {{ color: #b00020; font-weight: bold; }}
    code {{ background: #f7f7f7; padding: 2px 4px; }}
  </style>
</head>
<body>
  <h1>Baseline Report</h1>
  <div>Baseline: <code>{baseline_snapshot.tag}</code></div>
  <div>Current: <code>{current_snapshot.tag}</code></div>
  <div>Window: last {hours}h</div>
  <div>Status: <span class="{"pass" if passed else "fail"}">{"PASSED" if passed else "FAILED"}</span></div>

  <table>
    <thead>
      <tr>
        <th>Metric</th>
        <th>Baseline</th>
        <th>Current</th>
        <th>Change</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td>LLM p95 latency (ms)</td>
        <td>{baseline_snapshot.llm_latency_p95_ms:.0f}</td>
        <td>{current_snapshot.llm_latency_p95_ms:.0f}</td>
        <td>{fmt_pct(current_snapshot.llm_latency_p95_ms, baseline_snapshot.llm_latency_p95_ms)}</td>
      </tr>
      <tr>
        <td>Total cost (USD)</td>
        <td>{baseline_snapshot.total_cost_usd:.4f}</td>
        <td>{current_snapshot.total_cost_usd:.4f}</td>
        <td>{fmt_pct(current_snapshot.total_cost_usd, baseline_snapshot.total_cost_usd)}</td>
      </tr>
      <tr>
        <td>Cache hit rate</td>
        <td>{baseline_snapshot.cache_hit_rate:.1%}</td>
        <td>{current_snapshot.cache_hit_rate:.1%}</td>
        <td>{fmt_pct(current_snapshot.cache_hit_rate, baseline_snapshot.cache_hit_rate)}</td>
      </tr>
      <tr>
        <td>LLM calls</td>
        <td>{baseline_snapshot.llm_calls}</td>
        <td>{current_snapshot.llm_calls}</td>
        <td>{fmt_pct(current_snapshot.llm_calls, baseline_snapshot.llm_calls)}</td>
      </tr>
    </tbody>
  </table>

  <h2>Regressions</h2>
  <ul>
    {"".join(f"<li>{r}</li>" for r in regressions) if regressions else "<li>None</li>"}
  </ul>
</body>
</html>
"""

    report_path.write_text(html, encoding="utf-8")
    click.echo(f"Report saved to {report_path}")


if __name__ == "__main__":
    cli()
