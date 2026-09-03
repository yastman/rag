"""Telethon client wrapper for E2E testing."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

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


@dataclass
class ReceivedMessage:
    """Normalized incoming bot message observed during a journey step."""

    text: str
    message_id: int
    response_time_ms: int
    raw_message: Any = None
    button_labels: tuple[str, ...] = field(default_factory=tuple)
    has_reply_keyboard: bool = False
    reply_button_labels: tuple[str, ...] = field(default_factory=tuple)

    def button_labels_matching(self, locator: str) -> tuple[str, ...]:
        """Return button labels containing ``locator`` (case-insensitive)."""
        needle = locator.lower()
        return tuple(label for label in self.button_labels if needle in label.lower())


def _collect_button_labels(raw: Any) -> tuple[str, ...]:
    """Flatten inline button labels from a Telethon message (best effort)."""
    labels: list[str] = []
    buttons = getattr(raw, "buttons", None)
    if not buttons:
        return tuple(labels)
    for row in buttons:
        for button in row:
            text = getattr(button, "text", None)
            if text:
                labels.append(text)
    return tuple(labels)


def _has_reply_keyboard(raw: Any) -> bool:
    """Detect a persistent/reply keyboard on a Telethon message."""
    markup = getattr(raw, "reply_markup", None)
    if markup is None:
        return False
    class_name = type(markup).__name__
    return "Reply" in class_name and "Inline" not in class_name


def _collect_reply_button_labels(raw: Any) -> tuple[str, ...]:
    """Flatten reply-keyboard button labels from a Telethon message."""
    markup = getattr(raw, "reply_markup", None)
    rows = getattr(markup, "rows", None)
    if not rows:
        return ()
    labels: list[str] = []
    for row in rows:
        for button in getattr(row, "buttons", None) or []:
            text = getattr(button, "text", None)
            if text:
                labels.append(text)
    return tuple(labels)


class JourneyTimeout(RuntimeError):
    """Raised when a journey step does not reach a terminal response in time."""


class JourneyButtonNotFound(RuntimeError):
    """Raised when the expected inline/reply button is not present."""


class JourneySession:
    """Long-lived bot conversation driving the frozen demo journey (#3205).

    A single Telethon conversation stays open for the whole gate so no bot
    message is lost between steps: the demo search path sends status messages
    ("🔍 Ищу...") *before* the terminal catalog response, and the gate must
    observe and count every send (single-send counts).
    """

    def __init__(self, client: TelegramClient, bot_username: str, timeout: float = 90.0):
        self._client = client
        self._bot_username = bot_username
        self._timeout = timeout
        self._conv: Any = None
        self.received: list[ReceivedMessage] = []

    async def open(self) -> None:
        self._conv = self._client.conversation(self._bot_username, timeout=self._timeout)
        await self._conv.__aenter__()

    async def close(self) -> None:
        if self._conv is not None:
            await self._conv.__aexit__(None, None, None)
            self._conv = None

    async def send_text(self, text: str) -> None:
        """Send a text message (command or reply-keyboard button label)."""
        await self._conv.send_message(text)

    def find_message(self, message_id: int | None = None) -> ReceivedMessage:
        """Return a received message by id, or the latest one when omitted."""
        if message_id is None:
            if not self.received:
                raise JourneyButtonNotFound("No bot message received yet")
            return self.received[-1]
        for msg in reversed(self.received):
            if msg.message_id == message_id:
                return msg
        raise JourneyButtonNotFound(f"Message id={message_id} was not received in this journey")

    async def click_inline_button(
        self,
        locator: str,
        *,
        message_id: int | None = None,
        first: bool = False,
    ) -> str:
        """Click the first inline button whose label contains ``locator``.

        ``first=True`` clicks the very first button of the message (used for
        example-query buttons whose dynamic labels are not known in advance).
        Returns the clicked label so the artifact records the exact surface.
        """
        received = self.find_message(message_id)
        raw = received.raw_message
        buttons = getattr(raw, "buttons", None) if raw is not None else None
        if not buttons:
            raise JourneyButtonNotFound(
                f"Message id={received.message_id} has no inline buttons to click "
                f"(locator={locator!r})"
            )
        for row_index, row in enumerate(buttons):
            for col_index, button in enumerate(row):
                label = getattr(button, "text", "") or ""
                if first or (locator.lower() in label.lower()):
                    await raw.click(row_index, col_index)
                    return label
        raise JourneyButtonNotFound(
            f"No inline button matching locator={locator!r} on message "
            f"id={received.message_id} (labels={received.button_labels})"
        )

    async def collect_until_terminal(
        self,
        *,
        is_terminal: Callable[[str], bool],
        is_status: Callable[[str], bool] | None = None,
        timeout_s: float | None = None,
        settle: float = 2.5,
    ) -> list[ReceivedMessage]:
        """Collect incoming bot messages until the terminal predicate matches.

        Status messages (e.g. "🔍 Ищу подходящие варианты...") never satisfy
        the terminal predicate; after the first terminal message the session
        keeps draining for ``settle`` seconds to count any trailing sends
        (single-send evidence). Raises ``JourneyTimeout`` when nothing
        terminal arrives within ``timeout``.
        """
        effective_timeout = timeout_s or self._timeout
        collected: list[ReceivedMessage] = []
        deadline = time.monotonic() + effective_timeout
        step_started = time.monotonic()
        terminal_seen = False

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if terminal_seen:
                    break
                raise JourneyTimeout(
                    f"No terminal response within {effective_timeout:.0f}s "
                    f"(collected={len(collected)} status messages)"
                )
            try:
                raw = await self._conv.get_response(timeout=remaining)
            except TimeoutError:
                if terminal_seen:
                    break
                raise JourneyTimeout(
                    f"No terminal response within {effective_timeout:.0f}s "
                    f"(collected={len(collected)} status messages)"
                ) from None

            received = ReceivedMessage(
                text=getattr(raw, "text", "") or "",
                message_id=getattr(raw, "id", 0),
                response_time_ms=0,
                raw_message=raw,
                button_labels=_collect_button_labels(raw),
                has_reply_keyboard=_has_reply_keyboard(raw),
                reply_button_labels=_collect_reply_button_labels(raw),
            )
            self.received.append(received)
            collected.append(received)

            looks_status = is_status is not None and is_status(received.text)
            if not terminal_seen and not looks_status and is_terminal(received.text):
                terminal_seen = True
                received.response_time_ms = int((time.monotonic() - step_started) * 1000)
                # Drain only the settle window past the terminal response.
                deadline = min(deadline, time.monotonic() + settle)

        return collected

    async def __aenter__(self) -> JourneySession:
        await self.open()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.close()


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
        await self._client.connect()
        authorized = await self._client.is_user_authorized()
        if not authorized:
            await self._client.disconnect()
            raise RuntimeError(
                "Telethon session is not authorized. Run scripts/e2e/auth.py to refresh e2e_tester.session."
            )
        logger.info("Connected to Telegram (authorized=True)")

    async def disconnect(self) -> None:
        """Disconnect from Telegram."""
        if self._client:
            await self._client.disconnect()
            logger.info("Disconnected from Telegram")

    def journey(self) -> JourneySession:
        """Return a long-lived journey session (must be used after connect)."""
        if self._client is None:
            raise RuntimeError("Client not connected")
        return JourneySession(self._client, self.config.bot_username, self.config.response_timeout)

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

    async def send_voice_and_wait(
        self,
        response_timeout: int | None = None,
    ) -> BotResponse:
        """Send voice note to bot and wait for response.

        Args:
            response_timeout: Response timeout in seconds (default from config)

        Returns:
            BotResponse with text and timing

        Raises:
            RuntimeError: If voice note path is not configured or file does not exist.
            TimeoutError: If no response within timeout
        """
        if not self._client:
            raise RuntimeError("Client not connected")

        path = self.config.voice_note_path
        if not path:
            raise RuntimeError(
                "E2E_VOICE_NOTE_PATH is not set. "
                "Provide a local audio file path for voice-note scenarios."
            )

        from pathlib import Path as _Path

        if not _Path(path).exists():
            raise RuntimeError(
                f"Voice note fixture not found: {path}. "
                "Set E2E_VOICE_NOTE_PATH to an existing audio file."
            )

        effective_timeout = response_timeout or self.config.response_timeout

        start_time = time.time()

        async with self._client.conversation(
            self.config.bot_username,
            timeout=effective_timeout,
        ) as conv:
            await conv.send_file(path, voice_note=True)
            logger.debug(f"Sent voice note: {path}")

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
