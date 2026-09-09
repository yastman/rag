"""Unit tests for scripts/e2e/runner.py.

Tests group-selection, request assembly, judge verdict, and exit-code logic.
Mocks TelegramClient entirely — no real credentials needed.
"""

from __future__ import annotations

import dataclasses
import io
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from rich.console import Console

from scripts.e2e.claude_judge import CriterionScore, JudgeResult, PassthroughJudge
from scripts.e2e.config import E2EConfig
from scripts.e2e.report_generator import TestReport as E2EReport
from scripts.e2e.report_generator import TestResult as E2EResult
from scripts.e2e.scenarios import (
    SCENARIOS,
    get_scenario_by_id,
    get_scenarios_by_group,
)
from scripts.e2e.scenarios import TestGroup as ScenarioGroup
from scripts.e2e.scenarios import TestScenario as Scenario


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(**kwargs) -> E2EConfig:
    defaults = {"telegram_api_id": 1, "telegram_api_hash": "testhash", "bot_username": "@testbot"}
    defaults.update(kwargs)
    return E2EConfig(**defaults)


def _pass_judge_result(summary: str = "ok") -> JudgeResult:
    cs = CriterionScore(8, "ok")
    return JudgeResult(
        relevance=cs,
        completeness=cs,
        filter_accuracy=cs,
        tone_format=cs,
        no_hallucination=cs,
        total_score=8.0,
        passed=True,
        summary=summary,
    )


def _fail_judge_result(summary: str = "fail") -> JudgeResult:
    cs = CriterionScore(2, "fail")
    return JudgeResult(
        relevance=cs,
        completeness=cs,
        filter_accuracy=cs,
        tone_format=cs,
        no_hallucination=cs,
        total_score=2.0,
        passed=False,
        summary=summary,
    )


def _make_test_result(
    scenario: Scenario, passed: bool = True, error: str | None = None
) -> E2EResult:
    jr = _pass_judge_result() if passed else _fail_judge_result()
    return E2EResult(
        scenario=scenario,
        bot_response="some response" if passed else "",
        response_time_ms=500,
        judge_result=jr,
        error=error,
    )


# ---------------------------------------------------------------------------
# Group parsing
# ---------------------------------------------------------------------------


class TestGroupParsing:
    """--group argument selects the right scenarios."""

    def test_no_group_returns_all_scenarios(self):
        """When no group is specified, all SCENARIOS are used."""
        assert len(SCENARIOS) > 0, "SCENARIOS list must be non-empty"

    def test_group_smoke_subset(self):
        """get_scenarios_by_group returns only matching group."""
        immigration = get_scenarios_by_group(ScenarioGroup.IMMIGRATION)
        assert len(immigration) > 0
        assert all(s.group == ScenarioGroup.IMMIGRATION for s in immigration)

    def test_group_commands_subset(self):
        commands = get_scenarios_by_group(ScenarioGroup.COMMANDS)
        assert len(commands) > 0
        assert all(s.group == ScenarioGroup.COMMANDS for s in commands)

    def test_all_groups_are_proper_subsets(self):
        """Every defined group has at least one scenario, and is a subset of SCENARIOS."""
        scenario_ids = {s.id for s in SCENARIOS}
        for group in ScenarioGroup:
            group_scenarios = get_scenarios_by_group(group)
            for s in group_scenarios:
                assert s.id in scenario_ids

    def test_unknown_group_not_in_enum(self):
        """TestGroup enum does not have a 'nonexistent' value."""
        with pytest.raises((ValueError, KeyError)):
            ScenarioGroup("nonexistent_group_xyz")

    def test_get_scenario_by_id_found(self):
        scenario = get_scenario_by_id("0.1")
        assert scenario is not None
        assert scenario.id == "0.1"

    def test_get_scenario_by_id_not_found(self):
        scenario = get_scenario_by_id("999.999")
        assert scenario is None


# ---------------------------------------------------------------------------
# Request assembly (message sent to the bot)
# ---------------------------------------------------------------------------


class TestRequestAssembly:
    """The correct query is passed through to the bot client."""

    def test_text_scenario_query_preserved(self):
        """A text scenario carries its query string unchanged."""
        s = Scenario(
            id="3.1",
            name="Price max",
            query="квартиры до 80000 евро",
            group=ScenarioGroup.PRICE_FILTERS,
        )
        assert s.query == "квартиры до 80000 евро"
        assert s.delivery == "text"

    def test_voice_scenario_delivery_flag(self):
        """Voice scenarios have delivery=='voice'."""
        s = Scenario(
            id="8.1",
            name="Voice search",
            query="(voice) найди квартиру",
            group=ScenarioGroup.VOICE_TRANSCRIPTION,
            delivery="voice",
        )
        assert s.delivery == "voice"

    def test_text_delivery_is_default(self):
        """Default delivery is 'text'."""
        s = Scenario(id="x.1", name="test", query="hello", group=ScenarioGroup.COMMANDS)
        assert s.delivery == "text"

    @pytest.mark.asyncio
    async def test_run_single_test_sends_exact_query_and_configured_timeout(self):
        """run_single_test calls client.send_and_wait with exact query/timeout kwargs."""
        from scripts.e2e.runner import run_single_test

        scenario = Scenario(
            id="1.1",
            name="/start",
            query="/start",
            group=ScenarioGroup.COMMANDS,
            expected_keywords=["привет"],
            timeout=7,
        )

        mock_response = MagicMock()
        mock_response.text = "Привет! Я помогу вам с недвижимостью в Болгарии."
        mock_response.response_time_ms = 300

        mock_client = AsyncMock()
        mock_client.send_and_wait = AsyncMock(return_value=mock_response)

        mock_judge = AsyncMock()
        mock_judge.evaluate = AsyncMock(return_value=_pass_judge_result())

        progress = MagicMock()
        task_id = 0

        result = await run_single_test(
            client=mock_client,
            judge=mock_judge,
            scenario=scenario,
            progress=progress,
            task_id=task_id,
        )

        mock_client.send_and_wait.assert_awaited_once_with(
            query="/start",
            response_timeout=7,
        )
        assert result.bot_response == mock_response.text

    @pytest.mark.asyncio
    async def test_run_single_test_calls_send_voice_for_voice_delivery(self):
        """run_single_test calls client.send_voice_and_wait for voice delivery."""
        from scripts.e2e.runner import run_single_test

        scenario = Scenario(
            id="8.1",
            name="Voice",
            query="(voice) найди квартиру",
            group=ScenarioGroup.VOICE_TRANSCRIPTION,
            delivery="voice",
        )

        mock_response = MagicMock()
        mock_response.text = "Вот квартиры у моря"
        mock_response.response_time_ms = 800

        mock_client = AsyncMock()
        mock_client.send_voice_and_wait = AsyncMock(return_value=mock_response)

        mock_judge = AsyncMock()
        mock_judge.evaluate = AsyncMock(return_value=_pass_judge_result())

        progress = MagicMock()

        result = await run_single_test(
            client=mock_client,
            judge=mock_judge,
            scenario=scenario,
            progress=progress,
            task_id=0,
        )

        mock_client.send_voice_and_wait.assert_awaited_once()
        assert result.bot_response == mock_response.text


# ---------------------------------------------------------------------------
# Judge verdict
# ---------------------------------------------------------------------------


class TestJudgeVerdict:
    """PassthroughJudge verdict logic: PASS, FAIL, empty-response."""

    @pytest.mark.asyncio
    async def test_response_with_keywords_passes(self):
        cfg = _make_config()
        judge = PassthroughJudge(cfg)
        scenario = Scenario(
            id="0.1",
            name="Immigration",
            query="Digital Nomad виза",
            group=ScenarioGroup.IMMIGRATION,
            expected_keywords=["digital", "nomad", "виза"],
        )
        result = await judge.evaluate(
            scenario=scenario, bot_response="Виза Digital Nomad требует..."
        )
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_response_missing_keywords_fails(self):
        cfg = _make_config()
        judge = PassthroughJudge(cfg)
        scenario = Scenario(
            id="0.1",
            name="Immigration",
            query="Digital Nomad виза",
            group=ScenarioGroup.IMMIGRATION,
            expected_keywords=["digital", "nomad", "виза", "болгар"],
        )
        result = await judge.evaluate(scenario=scenario, bot_response="Погода сегодня хорошая")
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_empty_response_fails(self):
        cfg = _make_config()
        judge = PassthroughJudge(cfg)
        scenario = Scenario(
            id="1.1",
            name="/start",
            query="/start",
            group=ScenarioGroup.COMMANDS,
        )
        result = await judge.evaluate(scenario=scenario, bot_response="")
        assert result.passed is False
        assert result.total_score == 0.0

    @pytest.mark.asyncio
    async def test_whitespace_only_response_fails(self):
        cfg = _make_config()
        judge = PassthroughJudge(cfg)
        scenario = Scenario(
            id="1.1",
            name="/start",
            query="/start",
            group=ScenarioGroup.COMMANDS,
        )
        result = await judge.evaluate(scenario=scenario, bot_response="   \n  ")
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_timeout_result_not_passed(self):
        """run_single_test returns a not-passed result on TimeoutError."""
        from scripts.e2e.runner import run_single_test

        scenario = Scenario(
            id="1.1",
            name="/start",
            query="/start",
            group=ScenarioGroup.COMMANDS,
            timeout=5,
        )

        mock_client = AsyncMock()
        mock_client.send_and_wait = AsyncMock(side_effect=TimeoutError)
        mock_judge = AsyncMock()
        progress = MagicMock()

        result = await run_single_test(
            client=mock_client,
            judge=mock_judge,
            scenario=scenario,
            progress=progress,
            task_id=0,
        )

        assert result.judge_result.passed is False
        assert result.error == "Timeout"

    @pytest.mark.asyncio
    async def test_exception_result_not_passed(self):
        """run_single_test wraps unexpected exceptions into an error result."""
        from scripts.e2e.runner import run_single_test

        scenario = Scenario(
            id="1.1",
            name="/start",
            query="/start",
            group=ScenarioGroup.COMMANDS,
        )

        mock_client = AsyncMock()
        mock_client.send_and_wait = AsyncMock(side_effect=RuntimeError("connection refused"))
        mock_judge = AsyncMock()
        progress = MagicMock()

        result = await run_single_test(
            client=mock_client,
            judge=mock_judge,
            scenario=scenario,
            progress=progress,
            task_id=0,
        )

        assert result.judge_result.passed is False
        assert "connection refused" in result.error


# ---------------------------------------------------------------------------
# Gate exit code (pure policy owner)
# ---------------------------------------------------------------------------


class TestGateExitCode:
    """exit_code(report, GATING_POLICY) requires 100% of selected scenarios.

    The gate is green only when the selection is non-empty and every
    selected scenario passed. Tests assert against the real policy owner —
    they never restate the policy expression locally.
    """

    def _make_report(self, passed_flags: list[bool]) -> E2EReport:
        scenario = get_scenario_by_id("1.1")
        assert scenario is not None
        results = [_make_test_result(scenario, passed=p) for p in passed_flags]
        return E2EReport(
            timestamp=datetime.now(),
            bot_username="@testbot",
            judge_provider="passthrough",
            judge_mode="no-judge",
            litellm_route_proof=None,
            results=results,
            total_duration_ms=1000,
        )

    def test_all_selected_pass_exit_zero(self):
        """5/5 selected scenarios pass → exit 0."""
        from scripts.e2e.runner import GATING_POLICY, exit_code

        assert exit_code(self._make_report([True] * 5), GATING_POLICY) == 0

    def test_one_failure_in_five_exit_nonzero(self):
        """4 passed / 1 failed must be red — no pass-rate threshold survives."""
        from scripts.e2e.runner import GATING_POLICY, exit_code

        assert exit_code(self._make_report([True, True, True, True, False]), GATING_POLICY) == 1

    def test_empty_selection_exit_nonzero(self):
        """An empty selected set can never be green."""
        from scripts.e2e.runner import GATING_POLICY, exit_code

        assert exit_code(self._make_report([]), GATING_POLICY) == 1

    def test_blocked_scenario_exit_nonzero(self):
        """A blocked (observability-failed) result is not a pass for the gate."""
        from scripts.e2e.runner import GATING_POLICY, exit_code

        report = self._make_report([True])
        report.results[0].observability_ok = False
        assert report.results[0].passed is False
        assert exit_code(report, GATING_POLICY) == 1

    def test_gating_policy_has_no_threshold_knob(self):
        """The gating policy exposes no tunable percentage field."""
        from scripts.e2e.runner import GatingPolicy

        assert dataclasses.fields(GatingPolicy) == ()


# ---------------------------------------------------------------------------
# main() exit wiring (real CLI boundary)
# ---------------------------------------------------------------------------


class TestMainExitWiring:
    """Real main() wiring: selection, exact client kwargs, gate exit codes.

    E2ETelegramClient is replaced with an async mock so no credentials or
    network are needed; everything else (selection, run loop, judge,
    report generation, gate) is the real runner path.
    """

    OK_RESPONSE = "Привет! Чем могу помочь с недвижимостью в Болгарии?"
    FAIL_RESPONSE = "СЕКРЕТНОЕ_СОДЕРЖИМОЕ_90000"

    def _run_main(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
        responses: list[str],
        scenario_ids: list[str],
    ) -> tuple[AsyncMock, str, int]:
        from scripts.e2e import runner as runner_module

        mock_responses = []
        for text in responses:
            response = MagicMock()
            response.text = text
            response.response_time_ms = 100
            mock_responses.append(response)

        client = AsyncMock()
        client.send_and_wait = AsyncMock(side_effect=mock_responses)
        client.__aenter__.return_value = client

        monkeypatch.setattr(runner_module, "E2ETelegramClient", MagicMock(return_value=client))
        monkeypatch.setattr(
            runner_module,
            "E2EConfig",
            lambda: _make_config(between_tests_delay=0, reports_dir=str(tmp_path / "reports")),
        )
        captured = io.StringIO()
        monkeypatch.setattr(runner_module, "console", Console(file=captured, width=240))

        argv = ["runner.py"]
        for sid in scenario_ids:
            argv.extend(["--scenario", sid])
        argv.append("--no-judge")
        monkeypatch.setattr(sys, "argv", argv)

        with pytest.raises(SystemExit) as excinfo:
            runner_module.main()
        return client, captured.getvalue(), excinfo.value.code

    def test_main_four_of_five_selected_exits_nonzero(self, monkeypatch, tmp_path):
        """4 passed / 1 failed (80% pass rate) must exit nonzero through main()."""
        client, _out, code = self._run_main(
            monkeypatch,
            tmp_path,
            responses=[self.OK_RESPONSE] * 4 + [self.FAIL_RESPONSE],
            scenario_ids=["1.1", "1.1", "1.1", "1.1", "1.2"],
        )
        assert client.send_and_wait.await_count == 5
        assert code == 1

    def test_main_all_selected_pass_exits_zero_with_exact_kwargs(self, monkeypatch, tmp_path):
        """5/5 → exit 0, and the bot client got the exact query/timeout kwargs."""
        client, _out, code = self._run_main(
            monkeypatch,
            tmp_path,
            responses=[self.OK_RESPONSE],
            scenario_ids=["1.1"],
        )
        assert code == 0
        expected_timeout = get_scenario_by_id("1.1").timeout
        client.send_and_wait.assert_awaited_once_with(
            query="/start",
            response_timeout=expected_timeout,
        )

    def test_main_gate_failure_names_failed_ids_without_response_content(
        self, monkeypatch, tmp_path
    ):
        """A red gate names the failed scenario IDs and never echoes bot responses."""
        _client, out, code = self._run_main(
            monkeypatch,
            tmp_path,
            responses=[self.OK_RESPONSE, self.FAIL_RESPONSE],
            scenario_ids=["1.1", "1.2"],
        )
        assert code == 1
        assert "E2E gate failed" in out
        assert "1.2" in out
        assert self.FAIL_RESPONSE not in out


# ---------------------------------------------------------------------------
# Summary report redaction
# ---------------------------------------------------------------------------


class TestSummaryRedactedReport:
    """print_summary names failed/blocked scenario IDs without echoing content."""

    def test_failed_ids_listed_without_responses(self, monkeypatch):
        from scripts.e2e import runner as runner_module

        results = [
            _make_test_result(get_scenario_by_id("1.1"), passed=True),
            _make_test_result(get_scenario_by_id("1.2"), passed=False),
        ]
        results[1].bot_response = "СЕКРЕТНОЕ_СОДЕРЖИМОЕ_90000"
        report = E2EReport(
            timestamp=datetime.now(),
            bot_username="@testbot",
            judge_provider="passthrough",
            judge_mode="no-judge",
            litellm_route_proof=None,
            results=results,
            total_duration_ms=1000,
        )

        captured = io.StringIO()
        monkeypatch.setattr(runner_module, "console", Console(file=captured, width=240))
        runner_module.print_summary(report)
        out = captured.getvalue()

        assert "1.2" in out
        assert "СЕКРЕТНОЕ_СОДЕРЖИМОЕ_90000" not in out


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestConfigValidation:
    """E2EConfig.validation_errors() returns errors for missing credentials."""

    def test_missing_api_id_reports_error(self):
        cfg = E2EConfig(telegram_api_id=0, telegram_api_hash="hash", bot_username="@bot")
        errors = cfg.validation_errors(judge_required=False)
        assert any("TELEGRAM_API_ID" in e for e in errors)

    def test_missing_api_hash_reports_error(self):
        cfg = E2EConfig(telegram_api_id=1, telegram_api_hash="", bot_username="@bot")
        errors = cfg.validation_errors(judge_required=False)
        assert any("TELEGRAM_API_HASH" in e for e in errors)

    def test_valid_config_no_errors_no_judge(self):
        cfg = E2EConfig(telegram_api_id=1, telegram_api_hash="abc", bot_username="@bot")
        errors = cfg.validation_errors(judge_required=False)
        assert errors == []
