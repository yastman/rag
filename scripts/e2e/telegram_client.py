"""Telethon client wrapper for E2E testing."""

import asyncio
import logging
import time
from dataclasses import dataclass

from telethon import TelegramClient
from telethon.tl.types import Message

from .config import E2EConfig


logger = logging.getLogger(__name__)


@dataclass
class BotResponse:
    """Response from bot."""

    text: str
    message_id: int
    response_time_ms: int
    raw_message: Message | None = None


class E2ETelegramClient:
    """Telegram client for E2E testing."""

    def __init__(self, config: E2EConfig):
        """Initialize client."""
        self.config = config
        self._client: TelegramClient | None = None

    async def connect(self) -> None:
        """Connect to Telegram."""
        self._client = TelegramClient(
            self.config.telegram_session,
            self.config.telegram_api_id,
            self.config.telegram_api_hash,
        )
        await self._client.start()
        me = await self._client.get_me()
        logger.info(f"Connected as {me.username or me.phone}")

    async def disconnect(self) -> None:
        """Disconnect from Telegram."""
        if self._client:
            await self._client.disconnect()
            logger.info("Disconnected from Telegram")

    async def send_and_wait(
        self,
        query: str,
        response_timeout: int | None = None,
    ) -> BotResponse:
        """Send message to bot and wait for response.

        Args:
            query: Message to send
            response_timeout: Response timeout in seconds (default from config)

        Returns:
            BotResponse with text and timing

        Raises:
            TimeoutError: If no response within timeout
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        effective_timeout = response_timeout or self.config.response_timeout

        start_time = time.time()

        async with self._client.conversation(
            self.config.bot_username,
            timeout=effective_timeout,
        ) as conv:
            await conv.send_message(query)
            logger.debug(f"Sent: {query[:50]}...")

            # Wait for response (handles streaming - waits for final message)
            response = await conv.get_response()

            # For streaming bots, wait a bit more for edits to complete
            await asyncio.sleep(1.0)

            # Try to get the latest version of the message (after edits)
            try:
                final_response = await conv.get_edit(timeout=3)
                response = final_response
            except TimeoutError:
                # No edits, use original response
                pass

        end_time = time.time()
        response_time_ms = int((end_time - start_time) * 1000)

        logger.debug(f"Response ({response_time_ms}ms): {response.text[:100]}...")

        return BotResponse(
            text=response.text or "",
            message_id=response.id,
            response_time_ms=response_time_ms,
            raw_message=response,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
