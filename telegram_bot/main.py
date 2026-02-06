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

from .bot import PropertyBot
from .config import BotConfig
from .logging_config import setup_logging
from .observability import get_langfuse_client


def _retry_delays() -> tuple[float, float]:
    initial = float(os.getenv("BOT_START_RETRY_DELAY_SEC", "2"))
    max_delay = float(os.getenv("BOT_START_RETRY_MAX_SEC", "60"))
    return max(0.5, initial), max(max_delay, 1.0)


async def main():
    """Run bot."""
    # Setup structured logging
    # Use JSON format in production, plain text in development
    json_format = os.getenv("LOG_FORMAT", "json") == "json"
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_file = os.getenv("LOG_FILE")  # Optional: write logs to file

    setup_logging(level=log_level, json_format=json_format, log_file=log_file)
    logger = logging.getLogger(__name__)

    # Initialize Langfuse client with PII masking FIRST
    # This registers the SDK singleton with mask=... before any other code uses it
    _langfuse = get_langfuse_client()
    logger.debug("Langfuse client initialized with PII masking")

    # Load config
    config = BotConfig()

    # Validate config
    if not config.telegram_token:
        logger.error("TELEGRAM_BOT_TOKEN not set in .env")
        return

    if not config.llm_api_key:
        logger.warning("OPENAI_API_KEY not set - LLM will not work")

    # Create and start bot
    bot = PropertyBot(config)
    delay, max_delay = _retry_delays()

    try:
        while True:
            try:
                await bot.start()
                break
            except TelegramRetryAfter as e:
                retry_after = max(float(e.retry_after), delay)
                logger.warning(
                    f"Telegram rate limit during startup. Retrying in {retry_after:.1f}s"
                )
                await asyncio.sleep(retry_after)
                delay = min(max_delay, delay * 2)
            except (TelegramNetworkError, TelegramServerError, OSError) as e:
                logger.warning(
                    f"Temporary Telegram/network error during startup: {e}. "
                    f"Retrying in {delay:.1f}s"
                )
                await asyncio.sleep(delay)
                delay = min(max_delay, delay * 2)
            except (TelegramUnauthorizedError, TelegramConflictError):
                # Fatal configuration/runtime errors; let container restart policy handle it.
                raise
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
