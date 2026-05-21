"""Tests for Sentry integration in startup exception hooks (sys.excepthook, asyncio loop handler)."""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock, patch

import pytest


class TestSysExcepthookInstalled:
    """Verify sys.excepthook integration point exists in main."""

    def test_sys_excepthook_installed_in_main(self) -> None:
        """The main() function source must contain sys.excepthook assignment."""
        from telegram_bot.main import main

        source = inspect.getsource(main)
        assert "sys.excepthook" in source, (
            "sys.excepthook override is missing from telegram_bot.main.main()"
        )

    def test_sentry_capture_in_excepthook(self) -> None:
        """The excepthook code must call sentry_sdk.capture_exception."""
        from telegram_bot.main import main

        source = inspect.getsource(main)
        assert "sentry_sdk.capture_exception" in source


class TestLoopExceptionHandlerCallsSentry:
    """Verify _install_loop_exception_handler calls sentry_sdk.capture_exception."""

    @patch("telegram_bot.main.sentry_sdk.capture_exception")
    def test_loop_exception_handler_calls_sentry(
        self, mock_capture: MagicMock
    ) -> None:
        """When an exception is in the loop context, sentry_sdk.capture_exception is called."""
        from telegram_bot.main import _install_loop_exception_handler

        logger = MagicMock()
        loop = asyncio.new_event_loop()
        try:
            _install_loop_exception_handler(loop, logger)

            # Simulate an exception in the loop context
            test_exc = RuntimeError("test loop error")
            context = {"message": "test error", "exception": test_exc}
            loop.call_exception_handler(context)

            mock_capture.assert_called_once_with(test_exc)
            # Logger should also be called
            logger.exception.assert_called_once()
        finally:
            loop.close()

    @patch("telegram_bot.main.sentry_sdk.capture_exception")
    def test_loop_exception_handler_no_exception_skips_sentry(
        self, mock_capture: MagicMock
    ) -> None:
        """When no exception object is in context, sentry should NOT be called."""
        from telegram_bot.main import _install_loop_exception_handler

        logger = MagicMock()
        loop = asyncio.new_event_loop()
        try:
            _install_loop_exception_handler(loop, logger)

            context = {"message": "something went wrong"}
            loop.call_exception_handler(context)

            mock_capture.assert_not_called()
            logger.error.assert_called_once()
        finally:
            loop.close()
