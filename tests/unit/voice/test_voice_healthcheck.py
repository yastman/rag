"""Regression tests for the voice-agent container healthcheck."""

from __future__ import annotations

from src.voice.healthcheck import _cmdline_matches_voice_agent


def test_cmdline_matches_voice_agent_start_process() -> None:
    assert _cmdline_matches_voice_agent(["python", "-m", "src.voice.agent", "start"])


def test_cmdline_does_not_match_healthcheck_probe_itself() -> None:
    assert not _cmdline_matches_voice_agent(
        ["python", "-m", "src.voice.healthcheck", "src.voice.agent", "start"]
    )


def test_cmdline_does_not_match_rag_api_process() -> None:
    assert not _cmdline_matches_voice_agent(["python", "-m", "src.api.main"])
