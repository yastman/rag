"""Regression tests for the voice-agent container healthcheck (issue #1549)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.voice.healthcheck import (
    _cmdline_matches_voice_agent,
    is_voice_agent_running,
    main,
)


# ---------------------------------------------------------------------------
# _cmdline_matches_voice_agent
# ---------------------------------------------------------------------------


def test_cmdline_matches_voice_agent_start_process() -> None:
    """The expected container CMD matches."""
    assert _cmdline_matches_voice_agent(["python", "-m", "src.voice.agent", "start"])


def test_cmdline_does_not_match_healthcheck_probe_itself() -> None:
    """A healthcheck probe running -m src.voice.healthcheck must not self-match."""
    assert not _cmdline_matches_voice_agent(
        ["python", "-m", "src.voice.healthcheck", "src.voice.agent", "start"]
    )


def test_cmdline_does_not_match_rag_api_process() -> None:
    """The rag-api process on port 8080 must not match the voice-agent pattern."""
    assert not _cmdline_matches_voice_agent(["python", "-m", "src.api.main"])


def test_cmdline_does_not_match_without_start_subcommand() -> None:
    """Without the 'start' subcommand the cmdline is not the agent launcher."""
    assert not _cmdline_matches_voice_agent(["python", "-m", "src.voice.agent"])


def test_cmdline_does_not_match_empty() -> None:
    assert not _cmdline_matches_voice_agent([])


def test_cmdline_does_not_match_partial() -> None:
    """A truncated cmdline should not produce a false positive."""
    assert not _cmdline_matches_voice_agent(["python", "-m"])


def test_cmdline_does_not_match_wrong_module() -> None:
    """Only the exact voice.agent module should match."""
    assert not _cmdline_matches_voice_agent(["python", "-m", "src.voice.healthcheck", "start"])


# ---------------------------------------------------------------------------
# is_voice_agent_running
# ---------------------------------------------------------------------------


def test_is_voice_agent_running_with_agent_process(tmp_path: Path) -> None:
    """Returns True when a voice-agent process is present in the mock /proc tree."""
    _setup_proc_entry(tmp_path, "1", "python\0-m\0src.voice.agent\0start")

    assert is_voice_agent_running(proc_root=tmp_path, current_pid=999) is True


def test_is_voice_agent_running_no_agent(tmp_path: Path) -> None:
    """Returns False when no process matches the voice-agent pattern."""
    _setup_proc_entry(tmp_path, "1", "python\0-m\0src.api.main")

    assert is_voice_agent_running(proc_root=tmp_path, current_pid=999) is False


def test_is_voice_agent_running_empty_proc(tmp_path: Path) -> None:
    """Returns False when the proc root is empty."""
    assert is_voice_agent_running(proc_root=tmp_path, current_pid=999) is False


def test_is_voice_agent_running_skips_current_pid(tmp_path: Path) -> None:
    """The current PID (healthcheck probe) is excluded even if its cmdline matches."""
    cid = os.getpid()
    _setup_proc_entry(tmp_path, str(cid), "python\0-m\0src.voice.agent\0start")

    assert is_voice_agent_running(proc_root=tmp_path, current_pid=cid) is False


def test_is_voice_agent_running_non_digit_entry(tmp_path: Path) -> None:
    """Non-digit entries in /proc are silently skipped."""
    (tmp_path / "version").write_text("Linux")
    (tmp_path / "1").mkdir()
    (tmp_path / "1").joinpath("cmdline").write_bytes(b"python\0-m\0src.voice.agent\0start")

    assert is_voice_agent_running(proc_root=tmp_path, current_pid=999) is True


def test_is_voice_agent_running_unreadable_cmdline(tmp_path: Path) -> None:
    """If a cmdline file cannot be read, the entry is silently skipped."""
    pid_dir = tmp_path / "1"
    pid_dir.mkdir()
    # no cmdline written – reading will raise OSError

    assert is_voice_agent_running(proc_root=tmp_path, current_pid=999) is False


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_returns_zero_when_running() -> None:
    """main() returns 0 (healthy) when a voice-agent process exists."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.voice.healthcheck.is_voice_agent_running",
            lambda *_args, **_kwargs: True,
        )
        assert main() == 0


def test_main_returns_one_when_not_running() -> None:
    """main() returns 1 (unhealthy) when no voice-agent process exists."""
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "src.voice.healthcheck.is_voice_agent_running",
            lambda *_args, **_kwargs: False,
        )
        assert main() == 1


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _setup_proc_entry(proc_root: Path, pid: str, cmdline: str) -> None:
    pid_dir = proc_root / pid
    pid_dir.mkdir()
    pid_dir.joinpath("cmdline").write_bytes(cmdline.encode())
