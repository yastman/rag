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

from scripts.e2e.claude_judge import (
    CriterionScore,
    JudgeResult,
    PassthroughJudge,
    build_judge,
)
from scripts.e2e.config import E2EConfig
from scripts.e2e.report_generator import ReportGenerator, TestReport, TestResult
from scripts.e2e.scenarios import (
    SCENARIOS,
    TestGroup,
    get_scenario_by_id,
    get_scenarios_by_group,
)
from scripts.e2e.telegram_client import E2ETelegramClient


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
console = Console()


async def run_single_test(
    client: E2ETelegramClient,
    judge,
    scenario,
    progress,
    task_id,
) -> TestResult:
    """Run single test scenario."""
    progress.update(task_id, description=f"[cyan]{scenario.id}[/] {scenario.name}")

    try:
        # Determine scenario delivery for the message send path.
        delivery = getattr(scenario, "delivery", "text")

        # Send message and get response
        if delivery == "voice":
            response = await client.send_voice_and_wait(
                response_timeout=scenario.timeout,
            )
        else:
            response = await client.send_and_wait(
                query=scenario.query,
                response_timeout=scenario.timeout,
            )

        # Judge the response
        judge_result = await judge.evaluate(
            scenario=scenario,
            bot_response=response.text,
        )

        return TestResult(
            scenario=scenario,
            bot_response=response.text,
            response_time_ms=response.response_time_ms,
            judge_result=judge_result,
        )

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
    no_judge: bool = False,
    route_proof: dict[str, str | None] | None = None,
) -> TestReport:
    """Run all test scenarios."""
    results = []
    start_time = time.time()

    if no_judge:
        console.print("[yellow]No-judge mode: skipping LLM evaluation[/]")
    else:
        console.print(f"[cyan]Judge provider:[/] {config.judge_provider} ({config.judge_model})")
    if route_proof:
        console.print(
            "[cyan]LiteLLM route proof:[/] "
            f"{route_proof.get('alias')} -> {route_proof.get('route_model') or 'unresolved'} "
            f"({route_proof.get('info_url')})"
        )

    async with E2ETelegramClient(config) as client:
        judge = PassthroughJudge(config) if no_judge else build_judge(config)

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
        judge_provider=config.judge_provider,
        judge_mode="no-judge" if no_judge else "llm-judge",
        litellm_route_proof=route_proof,
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
    table.add_row("Bot Target", report.bot_username)
    table.add_row("Judge", f"{report.judge_provider} ({report.judge_mode})")
    if report.litellm_route_proof:
        table.add_row(
            "LiteLLM Route",
            (
                f"{report.litellm_route_proof.get('alias')} -> "
                f"{report.litellm_route_proof.get('route_model') or 'unresolved'}"
            ),
        )

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
        action="append",
        help="Run only specific scenario by ID (e.g., 3.1). Can be repeated.",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip LLM judge — pass any non-empty bot response (no judge credentials needed)",
    )
    parser.add_argument(
        "--judge-provider",
        type=str,
        choices=["litellm", "anthropic-direct"],
        help="Override E2E_JUDGE_PROVIDER for this run",
    )
    parser.add_argument(
        "--skip-qdrant-preflight",
        action="store_true",
        help="Skip Qdrant preflight check (for local debugging only)",
    )
    args = parser.parse_args()

    # Load config
    config = E2EConfig()
    if args.judge_provider:
        config.judge_provider = args.judge_provider
    errors = config.validation_errors(judge_required=not args.no_judge)
    if errors:
        console.print("[red]Configuration errors:[/]")
        for e in errors:
            console.print(f"  - {e}")
        sys.exit(1)

    # Select scenarios
    if args.scenario:
        scenarios = []
        for sid in args.scenario:
            scenario = get_scenario_by_id(sid)
            if not scenario:
                console.print(f"[red]Scenario {sid} not found[/]")
                sys.exit(1)
            scenarios.append(scenario)
    elif args.group:
        group = TestGroup(args.group)
        scenarios = get_scenarios_by_group(group)
    else:
        scenarios = SCENARIOS

    console.print(
        "\n[bold]Running "
        f"{len(scenarios)} E2E tests against {config.bot_username} "
        f"(judge={config.judge_provider}, mode={'no-judge' if args.no_judge else 'llm'})[/]\n"
    )

    # Qdrant preflight for RAG/apartment/voice scenarios
    needs_qdrant = any(s.group not in {TestGroup.COMMANDS, TestGroup.CHITCHAT} for s in scenarios)
    if needs_qdrant and not args.skip_qdrant_preflight:
        from scripts.e2e.qdrant_preflight import CollectionRequirement, run_qdrant_preflight

        requirements = (
            CollectionRequirement(
                name=config.qdrant_doc_collection,
                min_points=config.qdrant_min_doc_points,
                required_vectors=frozenset(
                    v.strip() for v in config.qdrant_doc_vectors.split(",") if v.strip()
                ),
            ),
            CollectionRequirement(
                name=config.qdrant_apartment_collection,
                min_points=config.qdrant_min_apartment_points,
                required_vectors=frozenset(
                    v.strip() for v in config.qdrant_apartment_vectors.split(",") if v.strip()
                ),
            ),
        )
        preflight = run_qdrant_preflight(qdrant_url=config.qdrant_url, requirements=requirements)
        if not preflight.ok:
            console.print("[red]Qdrant preflight failed:[/]")
            for line in preflight.message.splitlines():
                console.print(f"  {line}")
            sys.exit(1)
        console.print("[green]Qdrant preflight passed[/]")
        console.print()

    route_proof: dict[str, str | None] | None = None

    # Run tests
    try:
        report = asyncio.run(
            run_tests(
                config,
                scenarios,
                no_judge=args.no_judge,
                route_proof=route_proof,
            )
        )
    except RuntimeError as exc:
        console.print(f"[red]E2E runner blocked:[/] {exc}")
        sys.exit(1)

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
