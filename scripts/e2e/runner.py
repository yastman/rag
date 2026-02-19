#!/usr/bin/env python3
"""E2E test runner for Telegram bot."""

import argparse
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table


# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.e2e.claude_judge import ClaudeJudge, CriterionScore, JudgeResult, PassthroughJudge
from scripts.e2e.config import E2EConfig
from scripts.e2e.langfuse_trace_validator import (
    is_validation_enabled,
    validate_latest_trace,
)
from scripts.e2e.report_generator import ReportGenerator, TestReport, TestResult
from scripts.e2e.telegram_client import E2ETelegramClient
from scripts.e2e.test_scenarios import (
    SCENARIOS,
    TestGroup,
    get_scenario_by_id,
    get_scenarios_by_group,
)


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


async def run_single_test(
    client: E2ETelegramClient,
    judge: ClaudeJudge,
    scenario,
    progress,
    task_id,
    validate_traces: bool = False,
) -> TestResult:
    """Run single test scenario."""
    progress.update(task_id, description=f"[cyan]{scenario.id}[/] {scenario.name}")

    try:
        # Record start time for trace validation
        test_started_at = datetime.utcnow()

        # Send message and get response
        response = await client.send_and_wait(
            query=scenario.query,
            response_timeout=scenario.timeout,
        )

        # Validate Langfuse trace if enabled
        trace_validation = None
        if validate_traces:
            trace_validation = validate_latest_trace(
                started_at=test_started_at,
                should_skip_rag=bool(getattr(scenario, "should_skip_rag", False)),
                is_command=bool(getattr(scenario, "group", None) == TestGroup.COMMANDS),
                timeout_s=20.0,
            )
            if not trace_validation.ok:
                logger.warning(f"Trace validation failed: {trace_validation}")

        # Judge the response
        judge_result = await judge.evaluate(
            scenario=scenario,
            bot_response=response.text,
        )

        result = TestResult(
            scenario=scenario,
            bot_response=response.text,
            response_time_ms=response.response_time_ms,
            judge_result=judge_result,
        )
        if trace_validation is not None:
            result.langfuse_trace_id = trace_validation.trace_id
            result.observability_ok = trace_validation.ok
            result.missing_spans = sorted(trace_validation.missing_spans)
            result.missing_scores = sorted(trace_validation.missing_scores)
            if not trace_validation.ok:
                details = []
                if trace_validation.error:
                    details.append(trace_validation.error)
                if trace_validation.missing_spans:
                    details.append(f"missing_spans={sorted(trace_validation.missing_spans)}")
                if trace_validation.missing_scores:
                    details.append(f"missing_scores={sorted(trace_validation.missing_scores)}")
                result.error = (
                    (result.error + " | " if result.error else "")
                    + "Langfuse: "
                    + "; ".join(details)
                )

        return result

    except TimeoutError:
        return TestResult(
            scenario=scenario,
            bot_response="",
            response_time_ms=scenario.timeout * 1000,
            judge_result=JudgeResult(
                relevance=CriterionScore(0, "Timeout"),
                completeness=CriterionScore(0, "Timeout"),
                filter_accuracy=CriterionScore(0, "Timeout"),
                tone_format=CriterionScore(0, "Timeout"),
                no_hallucination=CriterionScore(0, "Timeout"),
                total_score=0.0,
                passed=False,
                summary="Test timed out waiting for bot response",
            ),
            error="Timeout",
        )
    except Exception as e:
        logger.exception(f"Error in test {scenario.id}")
        return TestResult(
            scenario=scenario,
            bot_response="",
            response_time_ms=0,
            judge_result=JudgeResult(
                relevance=CriterionScore(0, "Error"),
                completeness=CriterionScore(0, "Error"),
                filter_accuracy=CriterionScore(0, "Error"),
                tone_format=CriterionScore(0, "Error"),
                no_hallucination=CriterionScore(0, "Error"),
                total_score=0.0,
                passed=False,
                summary=f"Test failed with error: {e}",
            ),
            error=str(e),
        )


async def run_tests(
    config: E2EConfig,
    scenarios: list,
    validate_traces: bool = False,
    no_judge: bool = False,
) -> TestReport:
    """Run all test scenarios."""
    results = []
    start_time = time.time()

    if validate_traces:
        console.print("[yellow]Langfuse trace validation enabled[/]")
    if no_judge:
        console.print("[yellow]No-judge mode: skipping LLM evaluation[/]")

    async with E2ETelegramClient(config) as client:
        judge = PassthroughJudge(config) if no_judge else ClaudeJudge(config)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task_id = progress.add_task("Running tests...", total=len(scenarios))

            for scenario in scenarios:
                result = await run_single_test(
                    client=client,
                    judge=judge,
                    scenario=scenario,
                    progress=progress,
                    task_id=task_id,
                    validate_traces=validate_traces,
                )
                results.append(result)

                # Print immediate result
                status = "[green]PASS[/]" if result.passed else "[red]FAIL[/]"
                console.print(
                    f"  {status} {scenario.id} {scenario.name}: "
                    f"{result.judge_result.total_score:.1f}"
                )

                progress.advance(task_id)

                # Rate limiting
                await asyncio.sleep(config.between_tests_delay)

    total_duration_ms = int((time.time() - start_time) * 1000)

    return TestReport(
        timestamp=datetime.now(),
        bot_username=config.bot_username,
        results=results,
        total_duration_ms=total_duration_ms,
    )


def print_summary(report: TestReport):
    """Print test summary table."""
    console.print()

    table = Table(title="E2E Test Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="white")

    table.add_row("Total Tests", str(report.total_tests))
    table.add_row("Passed", f"[green]{report.passed_tests}[/]")
    table.add_row("Failed", f"[red]{report.failed_tests}[/]")
    table.add_row("Pass Rate", f"{report.pass_rate:.1f}%")
    table.add_row("Average Score", f"{report.average_score:.2f}")
    table.add_row("Duration", f"{report.total_duration_ms / 1000:.1f}s")

    console.print(table)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="E2E Test Runner")
    parser.add_argument(
        "--group",
        type=str,
        choices=[g.value for g in TestGroup],
        help="Run only specific test group",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Run only specific scenario by ID (e.g., 3.1)",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM judge — pass any non-empty bot response (no ANTHROPIC_API_KEY needed)",
    )
    args = parser.parse_args()

    # Load config
    config = E2EConfig()
    errors = config.validate()
    if args.no_judge:
        errors = [e for e in errors if "ANTHROPIC_API_KEY" not in e]
    if errors:
        console.print("[red]Configuration errors:[/]")
        for e in errors:
            console.print(f"  - {e}")
        sys.exit(1)

    # Select scenarios
    if args.scenario:
        scenario = get_scenario_by_id(args.scenario)
        if not scenario:
            console.print(f"[red]Scenario {args.scenario} not found[/]")
            sys.exit(1)
        scenarios = [scenario]
    elif args.group:
        group = TestGroup(args.group)
        scenarios = get_scenarios_by_group(group)
    else:
        scenarios = SCENARIOS

    console.print(f"\n[bold]Running {len(scenarios)} E2E tests against {config.bot_username}[/]\n")

    # Check if trace validation is enabled
    validate_traces = is_validation_enabled()

    # Run tests
    report = asyncio.run(
        run_tests(config, scenarios, validate_traces=validate_traces, no_judge=args.no_judge)
    )

    # Generate reports
    generator = ReportGenerator(config.reports_dir)
    json_path, html_path = generator.generate(report)

    # Print summary
    print_summary(report)

    console.print("\n[dim]Reports saved to:[/]")
    console.print(f"  JSON: {json_path}")
    console.print(f"  HTML: {html_path}")

    # Exit code based on pass rate
    sys.exit(0 if report.pass_rate >= 80 else 1)


if __name__ == "__main__":
    main()
