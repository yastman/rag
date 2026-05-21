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

import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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
def cleanup_modules():
    """Mirror the isolation fixture used in tests/unit/test_main.py."""
    tracked = (
        "telegram_bot.main",
        "telegram_bot.bot",
        "telegram_bot.config",
        "telegram_bot.logging_config",
    )
    originals = {name: sys.modules.get(name) for name in tracked}
    pkg = sys.modules.get("telegram_bot")
    had_main_attr = pkg is not None and hasattr(pkg, "main")
    original_main_attr = getattr(pkg, "main", None) if had_main_attr else None
    for name in tracked:
        sys.modules.pop(name, None)
    if pkg is not None and hasattr(pkg, "main"):
        delattr(pkg, "main")
    yield
    for name, module in originals.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    if pkg is not None:
        if had_main_attr:
            pkg.main = original_main_attr
        elif hasattr(pkg, "main"):
            delattr(pkg, "main")


def _build_main_mocks() -> tuple[AsyncMock, MagicMock, dict[str, MagicMock]]:
    """Build the standard set of mocks used by the main.py tests."""
    mock_property_bot_instance = AsyncMock()
    mock_property_bot = MagicMock(return_value=mock_property_bot_instance)
    mock_bot_config = MagicMock()
    mock_setup_logging = MagicMock()

    mock_bot_mod = MagicMock()
    mock_bot_mod.PropertyBot = mock_property_bot

    mock_config_mod = MagicMock()
    mock_config_mod.BotConfig = mock_bot_config

    mock_logging_config_mod = MagicMock()
    mock_logging_config_mod.setup_logging = mock_setup_logging

    mock_config_instance = MagicMock()
    mock_config_instance.telegram_token = "test-token"
    mock_config_instance.llm_api_key = "test-api-key"
    mock_bot_config.return_value = mock_config_instance

    return (
        mock_property_bot_instance,
        mock_property_bot,
        {
            "telegram_bot.bot": mock_bot_mod,
            "telegram_bot.config": mock_config_mod,
            "telegram_bot.logging_config": mock_logging_config_mod,
        },
    )


class TestFatalTelegramErrorTraceback:
    """Fatal Telegram errors (Unauthorized/Conflict) must be logged with traceback."""

    async def test_unauthorized_uses_logger_exception(self, cleanup_modules):
        from aiogram.exceptions import TelegramUnauthorizedError

        mock_bot_instance, _mock_bot_cls, sys_mocks = _build_main_mocks()
        # Use a real exception so logger.exception sees a usable __traceback__.
        unauthorized = TelegramUnauthorizedError(method=MagicMock(), message="bad token")
        mock_bot_instance.start = AsyncMock(side_effect=unauthorized)

        mock_logger = MagicMock()

        with (
            patch.dict(sys.modules, sys_mocks),
            patch("telegram_bot.observability._is_endpoint_reachable", return_value=True),
        ):
            from telegram_bot import main as main_module

            with patch.object(main_module.logging, "getLogger", return_value=mock_logger):
                with pytest.raises(TelegramUnauthorizedError):
                    await main_module.main()

        assert mock_logger.exception.called, (
            "Fatal Telegram errors (Unauthorized/Conflict) must be logged via "
            "logger.exception() so operators see the traceback in logs/bot-run.log"
        )
        # The fatal-error log must mention what happened.
        call_msgs = [c.args[0] for c in mock_logger.exception.call_args_list if c.args]
        assert any("Fatal Telegram error" in msg for msg in call_msgs), (
            "logger.exception() call must keep the existing 'Fatal Telegram error' "
            f"message for grep-ability; saw: {call_msgs!r}"
        )

    async def test_conflict_uses_logger_exception(self, cleanup_modules):
        from aiogram.exceptions import TelegramConflictError

        mock_bot_instance, _mock_bot_cls, sys_mocks = _build_main_mocks()
        conflict = TelegramConflictError(method=MagicMock(), message="already running")
        mock_bot_instance.start = AsyncMock(side_effect=conflict)

        mock_logger = MagicMock()

        with (
            patch.dict(sys.modules, sys_mocks),
            patch("telegram_bot.observability._is_endpoint_reachable", return_value=True),
        ):
            from telegram_bot import main as main_module

            with patch.object(main_module.logging, "getLogger", return_value=mock_logger):
                with pytest.raises(TelegramConflictError):
                    await main_module.main()

        assert mock_logger.exception.called, (
            "TelegramConflictError must be logged via logger.exception() so the "
            "stacktrace lands in logs/bot-run.log"
        )


class TestAsyncioLoopExceptionHandler:
    """main.py must install an asyncio loop exception handler that logs tracebacks."""

    async def test_loop_handler_installed(self, cleanup_modules):
        _mock_bot_instance, _mock_bot_cls, sys_mocks = _build_main_mocks()

        with (
            patch.dict(sys.modules, sys_mocks),
            patch("telegram_bot.observability._is_endpoint_reachable", return_value=True),
        ):
            from telegram_bot import main as main_module

            captured: dict[str, object] = {}

            real_get_running_loop = main_module.asyncio.get_running_loop

            def _spy_get_running_loop():
                loop = real_get_running_loop()
                captured.setdefault("loop", loop)
                return loop

            with patch.object(
                main_module.asyncio,
                "get_running_loop",
                side_effect=_spy_get_running_loop,
            ):
                await main_module.main()

            loop = captured.get("loop")
            assert loop is not None, (
                "main() must call asyncio.get_running_loop() so it can install "
                "an exception handler for background tasks"
            )
            handler = loop.get_exception_handler()
            assert handler is not None, (
                "main() must install a custom loop exception handler so unhandled "
                "asyncio task exceptions are logged with traceback"
            )

    async def test_loop_handler_logs_with_traceback(self, cleanup_modules):
        """The installed handler must call logger.exception (or use exc_info=True)."""
        _mock_bot_instance, _mock_bot_cls, sys_mocks = _build_main_mocks()

        mock_logger = MagicMock()

        with (
            patch.dict(sys.modules, sys_mocks),
            patch("telegram_bot.observability._is_endpoint_reachable", return_value=True),
        ):
            from telegram_bot import main as main_module

            captured_handler: dict[str, object] = {}
            real_get_running_loop = main_module.asyncio.get_running_loop

            def _spy_get_running_loop():
                loop = real_get_running_loop()
                captured_handler.setdefault("loop", loop)
                return loop

            with (
                patch.object(main_module.logging, "getLogger", return_value=mock_logger),
                patch.object(
                    main_module.asyncio,
                    "get_running_loop",
                    side_effect=_spy_get_running_loop,
                ),
            ):
                await main_module.main()

            loop = captured_handler.get("loop")
            assert loop is not None
            handler = loop.get_exception_handler()
            assert handler is not None

            # Reset call history so we only see what the handler logs.
            mock_logger.reset_mock()
            try:
                raise RuntimeError("background boom")
            except RuntimeError as exc:
                ctx = {
                    "message": "Unhandled exception in event loop",
                    "exception": exc,
                }
                handler(loop, ctx)

            assert mock_logger.exception.called or any(
                call.kwargs.get("exc_info") for call in mock_logger.error.call_args_list
            ), (
                "loop exception handler must use logger.exception() or "
                "logger.error(..., exc_info=...) so the traceback is captured"
            )
