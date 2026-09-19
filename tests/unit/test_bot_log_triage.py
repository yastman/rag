"""Contract tests for Issue #1418: bot log triage targets and traceback capture.

This file enforces:
- Makefile exposes operator-friendly bot log triage targets:
  ``bot-logs-tail``, ``bot-logs-errors``, ``bot-logs-startup``.
- ``make bot`` continues to write to ``logs/bot-run.log`` (the file the
  triage targets read from), so the user-facing workflow stays
  ``make bot`` -> ``make bot-logs-errors``.
- ``telegram_bot.main`` logs fatal Telegram errors with full traceback
  via ``logger.exception(...)`` so operators can debug auth/conflict
  failures from ``logs/bot-run.log`` without re-running the bot.
- ``telegram_bot.main`` installs an asyncio loop exception handler so
  background-task exceptions are not silently lost.
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.exceptions import TelegramConflictError, TelegramUnauthorizedError
from aiogram.methods import GetMe

from telegram_bot import main as main_module


MAKEFILE = Path("Makefile")


def _makefile_text() -> str:
    return MAKEFILE.read_text(encoding="utf-8")


def _target_block(target: str) -> str:
    """Return the recipe block for a Makefile target.

    Matches from ``<target>:`` up to the next target definition or EOF.
    """
    text = _makefile_text()
    block_match = re.search(
        rf"^{re.escape(target)}:.*?(?=^[A-Za-z0-9_.-]+:|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    assert block_match, f"Makefile target {target!r} not found"
    return block_match.group(0)


# ---------------------------------------------------------------------------
# Makefile contract
# ---------------------------------------------------------------------------


class TestBotLogTargetsExist:
    """All three log-triage targets must exist and be declared in .PHONY."""

    @pytest.mark.parametrize(
        "target",
        ["bot-logs-tail", "bot-logs-errors", "bot-logs-startup"],
    )
    def test_target_defined(self, target: str) -> None:
        text = _makefile_text()
        assert re.search(rf"^{re.escape(target)}:", text, re.MULTILINE), (
            f"Makefile target {target!r} must be defined for issue #1418"
        )

    @pytest.mark.parametrize(
        "target",
        ["bot-logs-tail", "bot-logs-errors", "bot-logs-startup"],
    )
    def test_target_phony(self, target: str) -> None:
        text = _makefile_text()
        # Robust regex that captures multi-line .PHONY blocks (continuation lines
        # ending with `\`). The historical pattern ``^\.PHONY:.*(?:\\\n.*)*``
        # silently fails on continuations because greedy ``.*`` swallows the
        # trailing backslash.
        phony_blocks = re.findall(r"^\.PHONY:(?:[^\n]*\\\n)*[^\n]*", text, re.MULTILINE)
        assert phony_blocks, ".PHONY declarations not found in Makefile"
        combined = " ".join(phony_blocks)
        assert target in combined, (
            f"{target!r} must be declared in .PHONY so the recipe runs even "
            f"when a same-named file exists in the repo"
        )

    @pytest.mark.parametrize(
        "target",
        ["bot-logs-tail", "bot-logs-errors", "bot-logs-startup"],
    )
    def test_target_has_help_doc(self, target: str) -> None:
        """Each target must include the `## help` annotation so it shows in `make help`."""
        text = _makefile_text()
        match = re.search(rf"^{re.escape(target)}:.*?##\s+(.+)$", text, re.MULTILINE)
        assert match, (
            f"Makefile target {target!r} must include a `## help` comment so it "
            f"appears in `make help` output"
        )
        help_text = match.group(1).strip()
        assert help_text, f"{target!r} help text must be non-empty"


class TestBotLogTargetsReadCorrectFile:
    """Each triage target must read from logs/bot-run.log (the `make bot` output)."""

    @pytest.mark.parametrize(
        "target",
        ["bot-logs-tail", "bot-logs-errors", "bot-logs-startup"],
    )
    def test_target_references_bot_run_log(self, target: str) -> None:
        block = _target_block(target)
        assert "logs/bot-run.log" in block, (
            f"{target!r} must read from logs/bot-run.log so it shares the "
            f"file written by `make bot`"
        )

    def test_bot_target_still_writes_bot_run_log(self) -> None:
        """`make bot` is the producer of logs/bot-run.log. Don't break that contract."""
        block = _target_block("bot")
        assert "logs/bot-run.log" in block, (
            "`make bot` must continue to tee to logs/bot-run.log so the "
            "log-triage targets work after a normal bot run"
        )

    def test_bot_target_creates_logs_dir(self) -> None:
        """`make bot` must keep `mkdir -p logs` so the tee target exists."""
        block = _target_block("bot")
        assert "mkdir -p logs" in block, (
            "`make bot` must keep `mkdir -p logs` so the tee target file path is always writable"
        )


class TestBotLogsTailSemantics:
    """`bot-logs-tail` must follow the live log file."""

    def test_uses_tail_follow(self) -> None:
        block = _target_block("bot-logs-tail")
        # tail -F preferred (handles log rotation); tail -f is acceptable too.
        assert re.search(r"\btail\s+-[fF]\b", block), (
            "bot-logs-tail must use `tail -f` (or `tail -F`) to stream the log file"
        )


class TestBotLogsErrorsSemantics:
    """`bot-logs-errors` must surface ERROR/CRITICAL/Traceback lines."""

    def test_filters_for_error_signals(self) -> None:
        block = _target_block("bot-logs-errors")
        # The recipe must look for at least one of the canonical error signals.
        # Accept either upper-case logging level or the structured JSON level
        # field, plus `Traceback` for stacktraces.
        canonical_signals = ("ERROR", "CRITICAL", "Traceback", "exception")
        present = [sig for sig in canonical_signals if sig in block]
        assert present, (
            f"bot-logs-errors must filter for at least one of "
            f"{canonical_signals!r} so operators see errors quickly"
        )

    def test_uses_grep_or_rg(self) -> None:
        block = _target_block("bot-logs-errors")
        assert re.search(r"\b(grep|rg)\b", block), (
            "bot-logs-errors must use `grep` or `rg` to filter the log file"
        )


class TestBotLogsStartupSemantics:
    """`bot-logs-startup` must surface boot-time / preflight events."""

    def test_filters_for_startup_signals(self) -> None:
        block = _target_block("bot-logs-startup")
        # Bot startup logs include "Startup verdict", "Preflight", or
        # "Logging configured" — at least one must appear.
        canonical_signals = ("Startup verdict", "Preflight", "Logging configured")
        present = [sig for sig in canonical_signals if sig in block]
        assert present, (
            f"bot-logs-startup must surface at least one of {canonical_signals!r} "
            f"so operators can find boot/preflight messages quickly"
        )


# ---------------------------------------------------------------------------
# main.py — fatal-error traceback capture
# ---------------------------------------------------------------------------


@pytest.fixture
async def runtime(monkeypatch):
    loop = asyncio.get_running_loop()
    previous_handler = loop.get_exception_handler()
    bot = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(main_module, "PropertyBot", lambda _config: bot)
    monkeypatch.setattr(
        main_module,
        "BotConfig",
        lambda: SimpleNamespace(telegram_token="test-token", llm_api_key="test-key"),
    )
    monkeypatch.setattr(main_module, "setup_logging", MagicMock())
    try:
        yield bot, loop
    finally:
        loop.set_exception_handler(previous_handler)


@pytest.mark.parametrize("error_type", [TelegramUnauthorizedError, TelegramConflictError])
async def test_fatal_telegram_error_logs_original_traceback(runtime, caplog, error_type):
    bot, _ = runtime
    error = error_type(method=GetMe(), message="fatal startup error")
    bot.start.side_effect = error
    with pytest.raises(error_type) as raised:
        await main_module.main()
    assert raised.value is error
    bot.start.assert_awaited_once()
    bot.stop.assert_awaited_once()
    record = next(record for record in caplog.records if "Fatal Telegram error" in record.message)
    assert record.exc_info is not None
    assert record.exc_info[1] is error
    assert record.exc_info[2] is not None


async def test_main_installs_loop_handler_and_logs_background_traceback(runtime, caplog):
    _, loop = runtime
    await main_module.main()
    handler = loop.get_exception_handler()
    assert handler is not None
    error = RuntimeError("background boom")
    with caplog.at_level(logging.ERROR):
        handler(loop, {"message": "Unhandled background task", "exception": error})
    record = next(record for record in caplog.records if "asyncio loop error" in record.message)
    assert "Unhandled background task" in record.message
    assert record.exc_info is not None
    assert record.exc_info[1] is error
    assert record.exc_info[2] is not None


async def test_loop_handler_logs_context_without_exception(runtime, caplog):
    _, loop = runtime
    await main_module.main()
    handler = loop.get_exception_handler()
    assert handler is not None
    handler(loop, {"message": "background warning", "task": "test-task"})
    assert "background warning" in caplog.text
    assert "test-task" in caplog.text
