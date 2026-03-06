"""Tests for demo handler FSM flow."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from telegram_bot.handlers.demo_handler import (
    DemoStates,
    handle_demo_apartments,
    handle_demo_button,
    handle_demo_search_text,
    handle_demo_search_voice,
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
                    "score": 0.85,
                    "payload": {
                        "complex_name": "Test",
                        "rooms": 1,
                        "price_eur": 90000,
                        "area_m2": 40,
                        "city": "Солнечный берег",
                    },
                    "id": "1",
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


class TestDemoVoiceFlow:
    """Voice messages in demo FSM state must go through demo pipeline, not main handle_voice."""

    async def test_demo_voice_calls_transcribe_and_pipeline(self) -> None:
        """Voice in demo mode → STT → pipeline.extract() → apartment search."""
        from telegram_bot.services.apartment_models import (
            ApartmentSearchFilters,
            ExtractionMeta,
            HardFilters,
        )

        message = AsyncMock()
        message.voice = AsyncMock()
        message.bot = AsyncMock()
        state = AsyncMock(spec=FSMContext)

        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=2, min_price_eur=200000, city="Солнечный берег"),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        apartments_service = AsyncMock()
        apartments_service.search_with_filters.return_value = (
            [
                {
                    "score": 0.9,
                    "payload": {
                        "complex_name": "Premier Fort Beach",
                        "rooms": 2,
                        "price_eur": 200000,
                        "area_m2": 79,
                        "city": "Солнечный берег",
                    },
                    "id": "1",
                }
            ],
            1,
        )
        embeddings = AsyncMock()
        embeddings.aembed_hybrid_with_colbert.return_value = ([0.1] * 1024, {}, [])

        transcribed = "Солнечный берег, квартиры дороже 200 тысяч евро"
        with patch(
            "telegram_bot.handlers.demo_handler.transcribe_voice",
            return_value=transcribed,
        ) as mock_transcribe:
            await handle_demo_search_voice(
                message,
                state,
                pipeline=pipeline,
                apartments_service=apartments_service,
                embeddings=embeddings,
            )
            mock_transcribe.assert_awaited_once_with(message, llm=None)

        pipeline.extract.assert_awaited_once_with(transcribed)
        apartments_service.search_with_filters.assert_awaited_once()

    async def test_demo_voice_shows_transcription(self) -> None:
        """Voice in demo shows '📝 Распознано: ...' before search."""
        message = AsyncMock()
        state = AsyncMock(spec=FSMContext)

        transcribed = "двушка до 100к"
        with patch(
            "telegram_bot.handlers.demo_handler.transcribe_voice",
            return_value=transcribed,
        ):
            await handle_demo_search_voice(message, state, pipeline=None)

        # First call: "🎤 Распознаю голос...", second: "📝 Распознано: ..."
        calls = message.answer.await_args_list
        assert any("Распознано" in str(c) and transcribed in str(c) for c in calls)

    async def test_demo_voice_failed_stt_shows_error(self) -> None:
        """If STT returns None, show error message."""
        message = AsyncMock()
        state = AsyncMock(spec=FSMContext)

        with patch(
            "telegram_bot.handlers.demo_handler.transcribe_voice",
            return_value=None,
        ):
            await handle_demo_search_voice(message, state, pipeline=AsyncMock())

        calls = message.answer.await_args_list
        assert any("Не удалось распознать" in str(c) for c in calls)

    async def test_demo_voice_passes_llm_to_transcribe(self) -> None:
        """Voice handler must pass injected llm client to transcribe_voice."""
        message = AsyncMock()
        state = AsyncMock(spec=FSMContext)
        llm = AsyncMock()

        with patch(
            "telegram_bot.handlers.demo_handler.transcribe_voice",
            return_value="test",
        ) as mock_transcribe:
            await handle_demo_search_voice(message, state, pipeline=None, llm=llm)
            mock_transcribe.assert_awaited_once_with(message, llm=llm)

    async def test_transcribe_voice_uses_injected_llm(self) -> None:
        """transcribe_voice must use injected llm, not create its own AsyncOpenAI."""
        from telegram_bot.handlers.demo_handler import transcribe_voice

        message = AsyncMock()
        message.voice = AsyncMock(file_id="f1")
        message.bot = AsyncMock()
        file_mock = AsyncMock()
        file_mock.file_path = "voice/test.ogg"
        message.bot.get_file.return_value = file_mock

        llm = AsyncMock()
        llm.audio.transcriptions.create.return_value = AsyncMock(text="hello")

        result = await transcribe_voice(message, llm=llm)

        assert result == "hello"
        llm.audio.transcriptions.create.assert_awaited_once()

    async def test_demo_router_registers_voice_handler(self) -> None:
        """Demo router must register voice handler for DemoStates.waiting_query."""
        from telegram_bot.handlers.demo_handler import create_demo_router

        router = create_demo_router()
        # Check that handle_demo_search_voice is registered
        handler_names = [h.callback.__name__ for h in router.message.handlers]
        assert "handle_demo_search_voice" in handler_names, (
            "Demo router must register handle_demo_search_voice"
        )


class TestHandleVoiceStateFilter:
    """Main handle_voice must NOT intercept voice during active FSM states."""

    def test_handle_voice_has_state_filter(self) -> None:
        """handle_voice registration must include StateFilter(None)
        to avoid intercepting voice messages during demo FSM state.
        Regression test for: voice in demo went to RAG instead of apartment search.
        """

        # Inspect _register_handlers source to find the voice registration
        import inspect

        from telegram_bot.bot import PropertyBot

        source = inspect.getsource(PropertyBot._register_handlers)
        # Must have StateFilter(None) alongside F.voice
        assert "StateFilter(None)" in source and "F.voice" in source, (
            "handle_voice must be registered with StateFilter(None) "
            "to prevent intercepting voice during FSM states (e.g. DemoStates.waiting_query)"
        )
