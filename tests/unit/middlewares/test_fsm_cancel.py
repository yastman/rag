"""Tests for FSMCancelMiddleware."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from telegram_bot.middlewares.fsm_cancel import FSMCancelMiddleware


def _make_message(text: str) -> MagicMock:
    msg = MagicMock()
    msg.text = text
    msg.answer = AsyncMock()
    return msg


def _make_state(current: str | None) -> MagicMock:
    state = MagicMock()
    state.get_state = AsyncMock(return_value=current)
    state.clear = AsyncMock()
    return state


class TestFSMCancelMiddleware:
    @pytest.fixture()
    def middleware(self):
        return FSMCancelMiddleware()

    @pytest.mark.asyncio()
    @pytest.mark.parametrize("text", ["/cancel", "Отмена", "отмена", "cancel", "❌ Отмена"])
    async def test_cancel_clears_fsm_state(self, middleware, text):
        msg = _make_message(text)
        state = _make_state("PhoneCollectorStates:waiting_phone")
        handler = AsyncMock()

        with patch("telegram_bot.middlewares.fsm_cancel.build_client_keyboard") as mock_kb:
            mock_kb.return_value = MagicMock()
            await middleware(handler, msg, {"state": state})

        state.clear.assert_awaited_once()
        msg.answer.assert_awaited_once()
        handler.assert_not_awaited()

    @pytest.mark.asyncio()
    async def test_no_fsm_state_passes_through(self, middleware):
        msg = _make_message("/cancel")
        state = _make_state(None)
        handler = AsyncMock()

        await middleware(handler, msg, {"state": state})

        state.clear.assert_not_awaited()
        handler.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_non_cancel_text_passes_through(self, middleware):
        msg = _make_message("Привет")
        state = _make_state("PhoneCollectorStates:waiting_phone")
        handler = AsyncMock()

        await middleware(handler, msg, {"state": state})

        state.clear.assert_not_awaited()
        handler.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_no_state_in_data_passes_through(self, middleware):
        msg = _make_message("/cancel")
        handler = AsyncMock()

        await middleware(handler, msg, {})

        handler.assert_awaited_once()

    @pytest.mark.asyncio()
    async def test_no_text_passes_through(self, middleware):
        msg = _make_message(None)
        state = _make_state("PhoneCollectorStates:waiting_phone")
        handler = AsyncMock()

        await middleware(handler, msg, {"state": state})

        handler.assert_awaited_once()
