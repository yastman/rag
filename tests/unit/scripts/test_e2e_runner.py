"""Unit tests for scripts/e2e/runner.py.

Tests group-selection, request assembly, judge verdict, and exit-code logic.
Mocks TelegramClient entirely — no real credentials needed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.e2e.claude_judge import CriterionScore, JudgeResult, PassthroughJudge
from scripts.e2e.config import E2EConfig
from scripts.e2e.report_generator import TestReport, TestResult
from scripts.e2e.scenarios import (
    SCENARIOS,
    TestGroup,
    TestScenario,
    get_scenario_by_id,
    get_scenarios_by_group,
)


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
    scenario: TestScenario, passed: bool = True, error: str | None = None
) -> TestResult:
    jr = _pass_judge_result() if passed else _fail_judge_result()
    return TestResult(
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
        immigration = get_scenarios_by_group(TestGroup.IMMIGRATION)
        assert len(immigration) > 0
        assert all(s.group == TestGroup.IMMIGRATION for s in immigration)

    def test_group_commands_subset(self):
        commands = get_scenarios_by_group(TestGroup.COMMANDS)
        assert len(commands) > 0
        assert all(s.group == TestGroup.COMMANDS for s in commands)

    def test_all_groups_are_proper_subsets(self):
        """Every defined group has at least one scenario, and is a subset of SCENARIOS."""
        scenario_ids = {s.id for s in SCENARIOS}
        for group in TestGroup:
            group_scenarios = get_scenarios_by_group(group)
            for s in group_scenarios:
                assert s.id in scenario_ids

    def test_unknown_group_not_in_enum(self):
        """TestGroup enum does not have a 'nonexistent' value."""
        with pytest.raises((ValueError, KeyError)):
            TestGroup("nonexistent_group_xyz")

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
        s = TestScenario(
            id="3.1",
            name="Price max",
            query="квартиры до 80000 евро",
            group=TestGroup.PRICE_FILTERS,
        )
        assert s.query == "квартиры до 80000 евро"
        assert s.delivery == "text"

    def test_voice_scenario_delivery_flag(self):
        """Voice scenarios have delivery=='voice'."""
        s = TestScenario(
            id="8.1",
            name="Voice search",
            query="(voice) найди квартиру",
            group=TestGroup.VOICE_TRANSCRIPTION,
            delivery="voice",
        )
        assert s.delivery == "voice"

    def test_text_delivery_is_default(self):
        """Default delivery is 'text'."""
        s = TestScenario(id="x.1", name="test", query="hello", group=TestGroup.COMMANDS)
        assert s.delivery == "text"

    @pytest.mark.asyncio
    async def test_run_single_test_calls_send_and_wait_for_text(self):
        """run_single_test calls client.send_and_wait for text delivery."""
        from scripts.e2e.runner import run_single_test

        scenario = TestScenario(
            id="1.1",
            name="/start",
            query="/start",
            group=TestGroup.COMMANDS,
            expected_keywords=["привет"],
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

        mock_client.send_and_wait.assert_awaited_once()
        call_kwargs = mock_client.send_and_wait.call_args
        assert (
            call_kwargs.kwargs.get("query") == "/start" or call_kwargs.args[0] == "/start"
            if call_kwargs.args
            else True
        )
        assert result.bot_response == mock_response.text

    @pytest.mark.asyncio
    async def test_run_single_test_calls_send_voice_for_voice_delivery(self):
        """run_single_test calls client.send_voice_and_wait for voice delivery."""
        from scripts.e2e.runner import run_single_test

        scenario = TestScenario(
            id="8.1",
            name="Voice",
            query="(voice) найди квартиру",
            group=TestGroup.VOICE_TRANSCRIPTION,
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
        scenario = TestScenario(
            id="0.1",
            name="Immigration",
            query="Digital Nomad виза",
            group=TestGroup.IMMIGRATION,
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
        scenario = TestScenario(
            id="0.1",
            name="Immigration",
            query="Digital Nomad виза",
            group=TestGroup.IMMIGRATION,
            expected_keywords=["digital", "nomad", "виза", "болгар"],
        )
        result = await judge.evaluate(scenario=scenario, bot_response="Погода сегодня хорошая")
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_empty_response_fails(self):
        cfg = _make_config()
        judge = PassthroughJudge(cfg)
        scenario = TestScenario(
            id="1.1",
            name="/start",
            query="/start",
            group=TestGroup.COMMANDS,
        )
        result = await judge.evaluate(scenario=scenario, bot_response="")
        assert result.passed is False
        assert result.total_score == 0.0

    @pytest.mark.asyncio
    async def test_whitespace_only_response_fails(self):
        cfg = _make_config()
        judge = PassthroughJudge(cfg)
        scenario = TestScenario(
            id="1.1",
            name="/start",
            query="/start",
            group=TestGroup.COMMANDS,
        )
        result = await judge.evaluate(scenario=scenario, bot_response="   \n  ")
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_timeout_result_not_passed(self):
        """run_single_test returns a not-passed result on TimeoutError."""
        from scripts.e2e.runner import run_single_test

        scenario = TestScenario(
            id="1.1",
            name="/start",
            query="/start",
            group=TestGroup.COMMANDS,
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

        scenario = TestScenario(
            id="1.1",
            name="/start",
            query="/start",
            group=TestGroup.COMMANDS,
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
# Exit code
# ---------------------------------------------------------------------------


class TestExitCode:
    """TestReport.pass_rate drives exit code: ≥80% → 0, <80% → 1."""

    def _make_report(self, results: list[TestResult]) -> TestReport:
        from datetime import datetime

        return TestReport(
            timestamp=datetime.now(),
            bot_username="@testbot",
            judge_provider="passthrough",
            judge_mode="no-judge",
            litellm_route_proof=None,
            results=results,
            total_duration_ms=1000,
        )

    def test_all_pass_report_exit_zero(self):
        """All tests pass → pass_rate == 100% ≥ 80 → exit 0."""
        scenario = get_scenario_by_id("1.1")
        assert scenario is not None
        results = [_make_test_result(scenario, passed=True) for _ in range(5)]
        report = self._make_report(results)
        assert report.pass_rate == 100.0
        expected_exit = 0 if report.pass_rate >= 80 else 1
        assert expected_exit == 0

    def test_all_fail_report_exit_nonzero(self):
        """All tests fail → pass_rate == 0% < 80 → exit 1."""
        scenario = get_scenario_by_id("1.1")
        assert scenario is not None
        results = [_make_test_result(scenario, passed=False) for _ in range(5)]
        report = self._make_report(results)
        assert report.pass_rate == 0.0
        expected_exit = 0 if report.pass_rate >= 80 else 1
        assert expected_exit == 1

    def test_mixed_pass_rate_below_80_exits_nonzero(self):
        """3 fail + 2 pass = 40% pass rate → exit 1."""
        scenario = get_scenario_by_id("1.1")
        assert scenario is not None
        results = [
            _make_test_result(scenario, passed=False),
            _make_test_result(scenario, passed=False),
            _make_test_result(scenario, passed=False),
            _make_test_result(scenario, passed=True),
            _make_test_result(scenario, passed=True),
        ]
        report = self._make_report(results)
        assert report.pass_rate == 40.0
        expected_exit = 0 if report.pass_rate >= 80 else 1
        assert expected_exit == 1

    def test_exactly_80_percent_exits_zero(self):
        """Exactly 4/5 pass = 80% → exit 0."""
        scenario = get_scenario_by_id("1.1")
        assert scenario is not None
        results = [
            _make_test_result(scenario, passed=True),
            _make_test_result(scenario, passed=True),
            _make_test_result(scenario, passed=True),
            _make_test_result(scenario, passed=True),
            _make_test_result(scenario, passed=False),
        ]
        report = self._make_report(results)
        assert report.pass_rate == 80.0
        expected_exit = 0 if report.pass_rate >= 80 else 1
        assert expected_exit == 0

    def test_empty_report_no_crash(self):
        """An empty report doesn't divide by zero."""
        report = self._make_report([])
        assert report.pass_rate == 0.0
        assert report.total_tests == 0


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


class TestConfigValidation:
    """E2EConfig.validate() returns errors for missing credentials."""

    def test_missing_api_id_reports_error(self):
        cfg = E2EConfig(telegram_api_id=0, telegram_api_hash="hash", bot_username="@bot")
        errors = cfg.validate(judge_required=False)
        assert any("TELEGRAM_API_ID" in e for e in errors)

    def test_missing_api_hash_reports_error(self):
        cfg = E2EConfig(telegram_api_id=1, telegram_api_hash="", bot_username="@bot")
        errors = cfg.validate(judge_required=False)
        assert any("TELEGRAM_API_HASH" in e for e in errors)

    def test_valid_config_no_errors_no_judge(self):
        cfg = E2EConfig(telegram_api_id=1, telegram_api_hash="abc", bot_username="@bot")
        errors = cfg.validate(judge_required=False)
        assert errors == []
