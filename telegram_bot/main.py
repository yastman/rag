#!/usr/bin/env python3
"""Telegram RAG bot entry point."""

import asyncio
import logging

from .bot import PropertyBot
from .config import BotConfig


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )


async def main():
    """Run bot."""
    setup_logging()
    logger = logging.getLogger(__name__)

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
    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    finally:
        await bot.stop()


if __name__ == "__main__":
    asyncio.run(main())
