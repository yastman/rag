"""E2E safety net for the kept surfaces (Epic #2843 / Issue #2850, #3215).

Surfaces tested:
  1. Apartment Filter Dialog — entry: handle_demo_button + handle_demo_apartments
  2. Manager Reply (Forum Topics) — entry: ForumBridge.relay_to_topic + relay_to_client

The Text RAG Chat surface (#3215) goes through the assistant core via the
supervisor (`telegram_bot/pipeline/supervisor.py`); the client-direct
pipeline surface was removed, and its one-answer-per-question contract is
covered by the supervisor unit tests.

Surfaces 1 and 2 require aiogram and are skipped in the lean venv;
they run under ``make test-unit-extras`` with ``--all-extras``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytestmark = [pytest.mark.e2e, pytest.mark.no_services]


# ---------------------------------------------------------------------------
# Surface 1: Apartment Filter Dialog
# ---------------------------------------------------------------------------


class TestApartmentFilterDialogSurface:
    """Happy-path coverage for the Apartment Filter Dialog surface.

    Skipped when aiogram is not installed (lean venv); runs under extras lane.
    """

    @pytest.fixture(autouse=True)
    def _require_aiogram(self) -> None:
        pytest.importorskip("aiogram", reason="aiogram not installed (use extras lane)")

    @pytest.mark.asyncio
    async def test_handle_demo_button_posts_menu(self) -> None:
        """handle_demo_button sends a reply with the demo keyboard markup."""
        from telegram_bot.handlers.demo_handler import handle_demo_button

        message = MagicMock()
        message.answer = AsyncMock()

        with patch(
            "telegram_bot.handlers.demo_handler.build_demo_menu",
            return_value=MagicMock(),
        ):
            await handle_demo_button(message)

        message.answer.assert_called_once()
        text_arg = message.answer.call_args.args[0]
        assert "Демонстрация" in text_arg

    @pytest.mark.asyncio
    async def test_handle_demo_apartments_starts_dialog(self) -> None:
        """handle_demo_apartments acknowledges callback and starts DemoSG.intro."""
        from telegram_bot.dialogs.states import DemoSG
        from telegram_bot.handlers.demo_handler import handle_demo_apartments

        callback = AsyncMock()
        callback.answer = AsyncMock()
        dialog_manager = AsyncMock()
        dialog_manager.start = AsyncMock()

        await handle_demo_apartments(callback, dialog_manager)

        callback.answer.assert_called_once()
        dialog_manager.start.assert_called_once()
        assert dialog_manager.start.call_args.args[0] == DemoSG.intro

    def test_create_demo_router_is_named_demo(self) -> None:
        """create_demo_router returns a Router named 'demo'."""
        from telegram_bot.handlers.demo_handler import create_demo_router

        router = create_demo_router()
        assert router.name == "demo"


# ---------------------------------------------------------------------------
# Surface 2: Manager Reply (Forum Topics)
# ---------------------------------------------------------------------------


class TestManagerReplySurface:
    """Happy-path coverage for the Manager Reply / Forum Topics surface.

    Skipped when aiogram is not installed (lean venv); runs under extras lane.
    """

    @pytest.fixture(autouse=True)
    def _require_aiogram(self) -> None:
        pytest.importorskip("aiogram", reason="aiogram not installed (use extras lane)")

    @pytest.fixture
    def mock_bot(self) -> MagicMock:
        bot = AsyncMock()
        bot.create_forum_topic = AsyncMock(return_value=MagicMock(message_thread_id=99))
        bot.copy_message = AsyncMock()
        bot.send_message = AsyncMock(return_value=MagicMock(message_thread_id=99, message_id=1))
        bot.close_forum_topic = AsyncMock()
        return bot

    @pytest.fixture
    def bridge(self, mock_bot: MagicMock):  # type: ignore[no-untyped-def]
        from telegram_bot.services.forum_bridge import ForumBridge

        return ForumBridge(bot=mock_bot, managers_group_id=-100500)

    @pytest.mark.asyncio
    async def test_relay_to_topic_forwards_client_message(
        self, bridge: object, mock_bot: MagicMock
    ) -> None:
        """relay_to_topic copies the client message into the manager topic."""
        await bridge.relay_to_topic(from_chat_id=555, message_id=10, topic_id=99)  # type: ignore[attr-defined]
        mock_bot.copy_message.assert_called_once_with(
            chat_id=-100500,
            from_chat_id=555,
            message_id=10,
            message_thread_id=99,
        )

    @pytest.mark.asyncio
    async def test_relay_to_client_sends_manager_reply(
        self, bridge: object, mock_bot: MagicMock
    ) -> None:
        """relay_to_client copies the manager reply back to the client chat."""
        await bridge.relay_to_client(topic_id=99, message_id=77, client_chat_id=555)  # type: ignore[attr-defined]
        mock_bot.copy_message.assert_called_once_with(
            chat_id=555,
            from_chat_id=-100500,
            message_id=77,
        )

    @pytest.mark.asyncio
    async def test_create_topic_and_relay_full_flow(
        self, bridge: object, mock_bot: MagicMock
    ) -> None:
        """Full manager-reply flow: create topic → relay client msg → relay manager reply."""
        topic_id = await bridge.create_topic(client_name="Анна", goal="Покупка")  # type: ignore[attr-defined]
        assert topic_id == 99

        await bridge.relay_to_topic(from_chat_id=123, message_id=1, topic_id=topic_id)  # type: ignore[attr-defined]
        await bridge.relay_to_client(topic_id=topic_id, message_id=2, client_chat_id=123)  # type: ignore[attr-defined]

        assert mock_bot.copy_message.call_count == 2

    @pytest.mark.asyncio
    async def test_start_qualification_without_dialog_manager_sends_fallback(
        self,
    ) -> None:
        """start_qualification falls back to a plain text reply when dialog_manager is None."""
        from aiogram.types import Message

        from telegram_bot.handlers.handoff import start_qualification

        message = AsyncMock(spec=Message)
        message.answer = AsyncMock()

        await start_qualification(message, dialog_manager=None)

        message.answer.assert_called_once()
        reply_text = message.answer.call_args.args[0]
        assert len(reply_text) > 0
