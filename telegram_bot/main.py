#!/usr/bin/env python3
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
from .logging_config import setup_logging
from .observability import initialize_langfuse


# Startup retry settings
_MAX_START_ATTEMPTS = int(os.getenv("BOT_START_MAX_ATTEMPTS", "10"))
_START_WAIT_MIN = float(os.getenv("BOT_START_RETRY_DELAY_SEC", "2"))
_START_WAIT_MAX = float(os.getenv("BOT_START_RETRY_MAX_SEC", "60"))


async def main():
    """Run bot."""
    # Setup structured logging
    json_format = os.getenv("LOG_FORMAT", "json") == "json"
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_file = os.getenv("LOG_FILE")

    setup_logging(level=log_level, json_format=json_format, log_file=log_file)
    logger = logging.getLogger(__name__)

    # Load config
    config = BotConfig()

    # Initialize Langfuse after BotConfig loaded .env / env vars
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
    except (TelegramUnauthorizedError, TelegramConflictError):
        logger.error("Fatal Telegram error — check bot token or stop other instances")
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
