"""Unit tests for no-judge passthrough mode."""

from __future__ import annotations

import asyncio

from scripts.e2e import test_scenarios as scenarios
from scripts.e2e.claude_judge import PassthroughJudge
from scripts.e2e.config import E2EConfig


def _scenario() -> scenarios.TestScenario:
    return scenarios.TestScenario(
        id="x",
        name="sample",
        query="query",
        group=scenarios.TestGroup.CHITCHAT,
    )


def test_passthrough_judge_passes_non_empty_short_response() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_scenario(), "ok"))

    assert result.passed is True
    assert result.total_score == 8.0


def test_passthrough_judge_fails_whitespace_response() -> None:
    judge = PassthroughJudge(E2EConfig())
    result = asyncio.run(judge.evaluate(_scenario(), "   "))

    assert result.passed is False
    assert result.total_score == 0.0
