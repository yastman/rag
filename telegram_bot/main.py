***REMOVED***!/usr/bin/env python3
"""Telegram RAG bot entry point."""

import asyncio
import logging
import os

from .bot import PropertyBot
from .config import BotConfig
from .logging_config import setup_logging


async def main():
    """Run bot."""
    ***REMOVED*** Setup structured logging
    ***REMOVED*** Use JSON format in production, plain text in development
    json_format = os.getenv("LOG_FORMAT", "json") == "json"
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_file = os.getenv("LOG_FILE")  ***REMOVED*** Optional: write logs to file

    setup_logging(level=log_level, json_format=json_format, log_file=log_file)
    logger = logging.getLogger(__name__)

    ***REMOVED*** Load config
    config = BotConfig()

    ***REMOVED*** Validate config
    if not config.telegram_token:
        logger.error("TELEGRAM_BOT_TOKEN not set in .env")
        return

    if not config.llm_api_key:
        logger.warning("OPENAI_API_KEY not set - LLM will not work")

    ***REMOVED*** Create and start bot
    bot = PropertyBot(config)
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
