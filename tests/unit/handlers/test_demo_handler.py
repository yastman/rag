"""Tests for demo handler FSM flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.handlers.demo_handler import (
    DemoStates,
    handle_demo_apartments,
    handle_demo_button,
    handle_demo_search_text,
)


class TestDemoFlow:
    @pytest.mark.asyncio
    async def test_demo_button_sends_inline_menu(self) -> None:
        message = AsyncMock()
        await handle_demo_button(message)
        message.answer.assert_awaited_once()
        call_kwargs = message.answer.await_args
        assert "Демонстрация" in call_kwargs.args[0]
        assert call_kwargs.kwargs.get("reply_markup") is not None

    @pytest.mark.asyncio
    async def test_demo_apartments_sets_fsm_state(self) -> None:
        callback = AsyncMock(spec=CallbackQuery)
        callback.answer = AsyncMock()
        callback.message = AsyncMock()
        state = AsyncMock(spec=FSMContext)
        await handle_demo_apartments(callback, state)
        state.set_state.assert_awaited_once_with(DemoStates.waiting_query)

    @pytest.mark.asyncio
    async def test_demo_apartments_shows_examples(self) -> None:
        callback = AsyncMock(spec=CallbackQuery)
        callback.answer = AsyncMock()
        callback.message = AsyncMock()
        state = AsyncMock(spec=FSMContext)
        await handle_demo_apartments(callback, state)
        sent = callback.message.answer.await_args
        assert "Напишите текстом" in sent.args[0]
        assert sent.kwargs.get("reply_markup") is not None

    @pytest.mark.asyncio
    async def test_demo_search_calls_pipeline(self) -> None:
        message = AsyncMock()
        message.text = "двушка до 100к"
        state = AsyncMock(spec=FSMContext)
        pipeline = AsyncMock()
        from telegram_bot.services.apartment_models import (
            ApartmentSearchFilters,
            ExtractionMeta,
            HardFilters,
        )

        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=2, max_price_eur=100000),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        await handle_demo_search_text(message, state, pipeline=pipeline)
        pipeline.extract.assert_awaited_once_with("двушка до 100к")


class TestDemoExampleClick:
    @pytest.mark.asyncio
    async def test_example_click_triggers_search(self) -> None:
        from telegram_bot.callback_data import DemoCB
        from telegram_bot.handlers.demo_handler import handle_demo_example
        from telegram_bot.services.apartment_models import (
            ApartmentSearchFilters,
            ExtractionMeta,
            HardFilters,
        )

        callback = AsyncMock(spec=CallbackQuery)
        callback.answer = AsyncMock()
        callback.message = AsyncMock()
        callback_data = DemoCB(action="example", idx=0)
        state = AsyncMock(spec=FSMContext)
        state.get_data.return_value = {"examples": ["Студия в Солнечном берегу до 100 000€"]}

        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=1, city="Солнечный берег", max_price_eur=100000),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        apartments_service = AsyncMock()
        apartments_service.search_with_filters.return_value = (
            [
                {
                    "complex_name": "Test",
                    "rooms": 1,
                    "price_eur": 90000,
                    "area_m2": 40,
                    "city": "Солнечный берег",
                }
            ],
            1,
        )
        embeddings = AsyncMock()
        embeddings.aembed_hybrid_with_colbert.return_value = ([0.1] * 1024, {}, [])

        await handle_demo_example(
            callback,
            callback_data,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
            embeddings=embeddings,
        )
        pipeline.extract.assert_awaited_once()
