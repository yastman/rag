"""CLI for baseline operations."""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

from .collector import LangfuseMetricsCollector
from .manager import BaselineManager, BaselineSnapshot


def get_collector() -> LangfuseMetricsCollector:
    """Create collector from environment."""
    return LangfuseMetricsCollector(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY", "pk-lf-dev"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY", "sk-lf-dev"),
        host=os.getenv("LANGFUSE_HOST", "http://localhost:3001"),
    )


def _metrics_to_snapshot(
    metrics,
    *,
    tag: str,
    session_id: str,
    ts,
) -> BaselineSnapshot:
    """Convert SessionMetrics to BaselineSnapshot without mixing tag/session semantics."""
    return BaselineSnapshot(
        timestamp=ts,
        tag=tag,
        session_id=session_id,
        llm_latency_p50_ms=metrics.llm_latency_p50_ms,
        llm_latency_p95_ms=metrics.llm_latency_p95_ms,
        full_rag_latency_p95_ms=metrics.llm_latency_p95_ms * 1.5,
        total_cost_usd=metrics.total_cost_usd,
        llm_tokens_input=metrics.llm_tokens_input,
        llm_tokens_output=metrics.llm_tokens_output,
        llm_calls=metrics.llm_calls,
        voyage_embed_calls=0,
        voyage_rerank_calls=0,
        cache_hit_rate=metrics.cache_hit_rate,
        cache_hits=metrics.cache_hits,
        cache_misses=metrics.cache_misses,
    )


def _print_comparison_table(baseline, current):
    """Print metrics comparison table."""

    def fmt_change(curr, base):
        if base == 0:
            return "N/A"
        pct = (curr / base - 1) * 100
        sign = "+" if pct >= 0 else ""
        return f"{sign}{pct:.1f}%"

    click.echo(f"\n{'Metric':<30} {'Baseline':<15} {'Current':<15} {'Change':<10}")
    click.echo("-" * 70)
    for label, b_val, c_val, fmt in [
        ("LLM p95 latency (ms)", baseline.llm_latency_p95_ms, current.llm_latency_p95_ms, ".0f"),
        ("Total cost (USD)", baseline.total_cost_usd, current.total_cost_usd, ".4f"),
        ("Cache hit rate", baseline.cache_hit_rate, current.cache_hit_rate, ".1%"),
        ("LLM calls", baseline.llm_calls, current.llm_calls, ""),
    ]:
        b_str = f"{b_val:{fmt}}" if fmt else str(b_val)
        c_str = f"{c_val:{fmt}}" if fmt else str(c_val)
        click.echo(f"{label:<30} {b_str:<15} {c_str:<15} {fmt_change(c_val, b_val):<10}")


@click.group()
def cli():
    """Baseline management CLI."""


@cli.command()
@click.option(
    "--baseline-tag", required=True, help="Langfuse tag for baseline traces (e.g. main-latest)"
)
@click.option("--current-session", required=True, help="Langfuse session_id for current CI run")
@click.option(
    "--thresholds",
    default="tests/baseline/thresholds.yaml",
    help="Path to thresholds file",
)
@click.option(
    "--output",
    required=True,
    help="Path to write JSON report artifact (always written)",
)
def compare(baseline_tag: str, current_session: str, thresholds: str, output: str):
    """Compare current run against baseline using per-trace metrics."""
    collector = get_collector()
    manager = BaselineManager(
        collector=collector,
        thresholds_path=Path(thresholds),
    )

    # Fetch baseline metrics by tag
    click.echo(f"Fetching baseline metrics (tag={baseline_tag})...")
    baseline_metrics = collector.collect_session_metrics(tag=baseline_tag)

    if baseline_metrics.trace_count == 0:
        result = {
            "status": "skipped",
            "reason": f"No baseline traces tagged '{baseline_tag}' found",
            "recommendation": "Run smoke tests on main branch first to establish baseline",
            "baseline_tag": baseline_tag,
            "current_session": current_session,
        }
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(result, indent=2))
        click.secho(f"SKIP — no baseline tagged '{baseline_tag}' found", fg="yellow")
        click.echo("Run smoke tests on main branch first to establish baseline.")
        sys.exit(0)

    # Fetch current metrics by session
    click.echo(f"Fetching current metrics (session={current_session})...")
    current_metrics = collector.collect_session_metrics(session_id=current_session)

    if current_metrics.trace_count == 0:
        result = {
            "status": "skipped",
            "reason": f"No traces found for session '{current_session}'",
            "baseline_tag": baseline_tag,
            "current_session": current_session,
        }
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(json.dumps(result, indent=2))
        click.secho(f"SKIP — no traces for session '{current_session}'", fg="yellow")
        sys.exit(0)

    # Build snapshots from session metrics
    now = datetime.now(UTC)
    baseline_snapshot = _metrics_to_snapshot(
        baseline_metrics,
        tag=baseline_tag,
        session_id=f"baseline:{baseline_tag}",
        ts=now,
    )
    current_snapshot = _metrics_to_snapshot(
        current_metrics,
        tag=current_session,
        session_id=current_session,
        ts=now,
    )

    # Compare
    click.echo("\nComparing metrics...")
    passed, regressions = manager.compare(current_snapshot, baseline_snapshot)

    # Print table
    _print_comparison_table(baseline_snapshot, current_snapshot)

    # Write JSON report
    report = {
        "status": "passed" if passed else "failed",
        "baseline_tag": baseline_tag,
        "current_session": current_session,
        "baseline_traces": baseline_metrics.trace_count,
        "current_traces": current_metrics.trace_count,
        "regressions": regressions,
        "metrics": {
            "baseline": {
                "llm_latency_p95_ms": baseline_snapshot.llm_latency_p95_ms,
                "total_cost_usd": baseline_snapshot.total_cost_usd,
                "cache_hit_rate": baseline_snapshot.cache_hit_rate,
                "llm_calls": baseline_snapshot.llm_calls,
            },
            "current": {
                "llm_latency_p95_ms": current_snapshot.llm_latency_p95_ms,
                "total_cost_usd": current_snapshot.total_cost_usd,
                "cache_hit_rate": current_snapshot.cache_hit_rate,
                "llm_calls": current_snapshot.llm_calls,
            },
        },
    }
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(report, indent=2))

    click.echo("\n" + "=" * 60)
    if passed:
        click.secho("PASSED — No regressions detected", fg="green", bold=True)
        sys.exit(0)
    else:
        click.secho("FAILED — Regressions detected:", fg="red", bold=True)
        for regression in regressions:
            click.echo(f"  - {regression}")
        sys.exit(1)


@cli.command("set-baseline")
@click.option("--tag", required=True, help="Tag to apply as baseline marker")
@click.option("--session-id", required=True, help="Session ID whose traces to tag")
def set_baseline(tag: str, session_id: str):
    """Tag traces from a session as the new baseline."""
    collector = get_collector()
    traces = collector._fetch_all_traces(session_id=session_id)

    if not traces:
        click.secho(f"No traces found for session '{session_id}'", fg="red")
        sys.exit(1)

    click.echo(f"Tagging {len(traces)} traces with '{tag}'...")
    for trace in traces:
        existing_tags = list(trace.tags or [])
        if tag not in existing_tags:
            existing_tags.append(tag)
            collector.client.api.trace.update(
                trace_id=trace.id,
                tags=existing_tags,
            )

    click.secho(f"Baseline set: {len(traces)} traces tagged '{tag}'", fg="green")


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
    from datetime import timedelta

    baseline = baseline or os.getenv("BASELINE_TAG")
    current = current or os.getenv("CURRENT_TAG")

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
