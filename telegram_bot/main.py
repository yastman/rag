***REMOVED***!/usr/bin/env python3
"""Telegram RAG bot entry point."""

import asyncio
import logging
import os

from aiogram.exceptions import (
    TelegramConflictError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    TelegramUnauthorizedError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .bot import PropertyBot
from .config import BotConfig
from .integrations.polling_lock import PollingLockBusy
from .logging_config import setup_logging
from .observability import initialize_langfuse


***REMOVED*** Startup retry settings
_MAX_START_ATTEMPTS = int(os.getenv("BOT_START_MAX_ATTEMPTS", "10"))
_START_WAIT_MIN = float(os.getenv("BOT_START_RETRY_DELAY_SEC", "2"))
_START_WAIT_MAX = float(os.getenv("BOT_START_RETRY_MAX_SEC", "60"))


def _install_loop_exception_handler(
    loop: asyncio.AbstractEventLoop, logger: logging.Logger
) -> None:
    """Install a loop-level exception handler that logs unhandled task errors with traceback.

    Without this hook, exceptions raised inside background asyncio tasks are
    surfaced via the default ``call_exception_handler`` and may not include a
    full stacktrace in operator log files. The custom handler re-raises the
    captured exception so ``logger.exception(...)`` records the traceback into
    ``logs/bot-run.log``, satisfying the issue ***REMOVED***1418 triage workflow.
    """

    def _handle_loop_exception(
        _loop: asyncio.AbstractEventLoop, context: dict[str, object]
    ) -> None:
        message = str(context.get("message", "Unhandled exception in event loop"))
        exception = context.get("exception")
        if isinstance(exception, BaseException):
            try:
                raise exception
            except BaseException:
                logger.exception("asyncio loop error: %s", message)
        else:
            logger.error("asyncio loop error: %s | context=%r", message, context)

    loop.set_exception_handler(_handle_loop_exception)


async def main():
    """Run bot."""
    ***REMOVED*** Setup structured logging
    json_format = os.getenv("LOG_FORMAT", "json") == "json"
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_file = os.getenv("LOG_FILE")

    setup_logging(level=log_level, json_format=json_format, log_file=log_file)
    logger = logging.getLogger(__name__)

    ***REMOVED*** Install asyncio loop exception handler so background-task crashes are
    ***REMOVED*** logged with full traceback (issue ***REMOVED***1418).
    try:
        _install_loop_exception_handler(asyncio.get_running_loop(), logger)
    except RuntimeError:
        ***REMOVED*** No running loop (synchronous test caller) — skip silently.
        logger.debug("Skipping loop exception handler install: no running loop")

    ***REMOVED*** Load config
    config = BotConfig()

    ***REMOVED*** Initialize Langfuse after BotConfig loaded .env / env vars
    _langfuse = initialize_langfuse(
        public_key=config.langfuse_public_key,
        secret_key=config.langfuse_secret_key,
        host=config.langfuse_host,
    )
    if _langfuse:
        logger.info("Langfuse client initialized with PII masking")
    else:
        logger.info("Langfuse disabled (missing LANGFUSE_PUBLIC_KEY/LANGFUSE_SECRET_KEY)")

    if not config.telegram_token:
        logger.error("TELEGRAM_BOT_TOKEN not set in .env")
        return

    if not config.llm_api_key:
        logger.warning("OPENAI_API_KEY not set - LLM will not work")

    bot = PropertyBot(config)

    @retry(
        retry=retry_if_exception_type(
            (TelegramRetryAfter, TelegramNetworkError, TelegramServerError, OSError)
        ),
        stop=stop_after_attempt(_MAX_START_ATTEMPTS),
        wait=wait_exponential(min=_START_WAIT_MIN, max=_START_WAIT_MAX),
        reraise=True,
    )
    async def _start_with_retry():
        await bot.start()

    try:
        await _start_with_retry()
    except PollingLockBusy as exc:
        logger.error("Polling lock is busy; another bot instance is active: %s", exc)
        raise SystemExit(2) from None
    except (TelegramUnauthorizedError, TelegramConflictError):
        ***REMOVED*** Use logger.exception so the full traceback lands in logs/bot-run.log
        ***REMOVED*** for the `make bot-logs-errors` triage workflow (issue ***REMOVED***1418).
        logger.exception("Fatal Telegram error — check bot token or stop other instances")
        raise
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        await bot.stop()


if __name__ == "__main__":
    try:
        import uvloop

        uvloop.install()
    except ImportError:
        pass
    asyncio.run(main())
