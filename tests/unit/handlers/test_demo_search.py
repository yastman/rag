"""Tests for demo search — text and voice input → results."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from telegram_bot.handlers.demo_handler import handle_demo_search_text
from telegram_bot.services.apartment_models import (
    ApartmentSearchFilters,
    ExtractionMeta,
    HardFilters,
)


class TestDemoSearchText:
    @pytest.mark.asyncio
    async def test_extracts_and_searches(self) -> None:
        message = AsyncMock()
        message.text = "двушка до 100к"
        state = AsyncMock()

        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=2, max_price_eur=100000),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )

        apartments_service = AsyncMock()
        apartments_service.scroll_with_filters.return_value = (
            [
                {
                    "payload": {
                        "complex_name": "Test",
                        "rooms": 2,
                        "price_eur": 95000,
                        "area_m2": 60,
                        "city": "Солнечный берег",
                    },
                    "id": "1",
                }
            ],
            1,
            95000.0,
            ["1"],
        )

        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
        )
        pipeline.extract.assert_awaited_once_with("двушка до 100к")
        message.answer.assert_awaited()
        kwargs = state.update_data.await_args.kwargs
        assert kwargs["catalog_runtime"]["total"] == 1

    @pytest.mark.asyncio
    async def test_low_confidence_still_searches(self) -> None:
        message = AsyncMock()
        message.text = "что-нибудь красивое"
        state = AsyncMock()

        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            meta=ExtractionMeta(source="llm", confidence="LOW"),
        )

        apartments_service = AsyncMock()
        apartments_service.scroll_with_filters.return_value = ([], 0, None, [])

        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
        )
        apartments_service.scroll_with_filters.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_pipeline_returns_error(self) -> None:
        message = AsyncMock()
        message.text = "двушка"
        state = AsyncMock()

        await handle_demo_search_text(message, state, pipeline=None)
        message.answer.assert_awaited_once()
        args = message.answer.await_args.args[0]
        assert "недоступен" in args


class TestDemoSearchEdgeCases:
    @pytest.mark.asyncio
    async def test_no_text_returns_prompt(self) -> None:
        """Empty text message shows guidance."""
        message = AsyncMock()
        message.text = None
        state = AsyncMock()
        await handle_demo_search_text(message, state, pipeline=AsyncMock())
        args = message.answer.await_args.args[0]
        assert "текстовое" in args

    @pytest.mark.asyncio
    async def test_no_service_shows_extraction(self) -> None:
        """Pipeline works but no apartments_service — shows extracted filters."""
        message = AsyncMock()
        message.text = "двушка до 100к"
        state = AsyncMock()
        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=2, max_price_eur=100000),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=None,
        )
        calls = [c.args[0] for c in message.answer.await_args_list]
        assert any("Распознано" in c or "тестовом" in c for c in calls)

    @pytest.mark.asyncio
    async def test_empty_results_shows_not_found(self) -> None:
        """Search returns 0 results — shows 'not found' message."""
        message = AsyncMock()
        message.text = "пентхаус в Бургасе"
        state = AsyncMock()
        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        apartments_service = AsyncMock()
        apartments_service.scroll_with_filters.return_value = ([], 0, None, [])

        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
        )
        calls = [c.args[0] for c in message.answer.await_args_list]
        assert any("не найдено" in c for c in calls)

    @pytest.mark.asyncio
    async def test_results_formatted_with_details(self) -> None:
        """Search results include complex name, price, area (HTML format)."""
        message = AsyncMock()
        message.text = "двушка"
        state = AsyncMock()
        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=2),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        apartments_service = AsyncMock()
        apartments_service.scroll_with_filters.return_value = (
            [
                {
                    "payload": {
                        "complex_name": "Fort Beach",
                        "rooms": 2,
                        "price_eur": 95000,
                        "area_m2": 60,
                        "city": "Солнечный берег",
                    },
                    "id": "1",
                }
            ],
            1,
            95000.0,
            ["1"],
        )
        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
        )
        calls = [c.args[0] for c in message.answer.await_args_list]
        result_msg = [c for c in calls if "Fort Beach" in c]
        assert len(result_msg) == 1
        assert "м²" in result_msg[0]
        assert "€" in result_msg[0]


class TestDemoResultsFormatting:
    """Tests for _run_demo_search result formatting via format_apartment_list (HTML)."""

    @staticmethod
    def _make_result(payload: dict, score: float = 0.8, rid: str = "1") -> dict:
        return {"score": score, "payload": payload, "id": rid}

    @staticmethod
    async def _run(results: list[dict], count: int) -> list[str]:
        message = AsyncMock()
        message.text = "тест"
        state = AsyncMock()
        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(),
            meta=ExtractionMeta(source="llm", confidence="HIGH"),
        )
        svc = AsyncMock()
        svc.scroll_with_filters.return_value = (results, count, 80000.0, [r["id"] for r in results])
        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=svc,
        )
        return [c.args[0] for c in message.answer.await_args_list]

    @pytest.mark.asyncio
    async def test_partial_payload_uses_defaults(self) -> None:
        """Missing payload fields — name shown, format doesn't crash."""
        results = [self._make_result({"complex_name": "Beach"})]
        calls = await self._run(results, 1)
        result_msg = [c for c in calls if "Beach" in c]
        assert len(result_msg) == 1
        assert "€" in result_msg[0]

    @pytest.mark.asyncio
    async def test_empty_payload_all_defaults(self) -> None:
        """Result with empty payload renders without crash."""
        results = [self._make_result({})]
        calls = await self._run(results, 1)
        # format_apartment_list handles empty payload gracefully
        assert len(calls) >= 2  # "Ищу..." + results

    @pytest.mark.asyncio
    async def test_missing_payload_key_graceful(self) -> None:
        """Result dict without 'payload' key doesn't crash."""
        results = [{"score": 0.5, "id": "x"}]
        calls = await self._run(results, 1)
        assert len(calls) >= 2  # "Ищу..." + results

    @pytest.mark.asyncio
    async def test_multiple_results_numbered(self) -> None:
        """Multiple results are numbered 1-N with correct data (HTML bold)."""
        results = [
            self._make_result(
                {"complex_name": "Alpha", "rooms": 1, "price_eur": 50000, "area_m2": 30}, rid="a"
            ),
            self._make_result(
                {"complex_name": "Beta", "rooms": 3, "price_eur": 200000, "area_m2": 90}, rid="b"
            ),
            self._make_result(
                {"complex_name": "Gamma", "rooms": 2, "price_eur": 120000, "area_m2": 65},
                rid="c",
            ),
        ]
        calls = await self._run(results, 3)
        result_msg = [c for c in calls if "Alpha" in c]
        assert len(result_msg) == 1
        text = result_msg[0]
        assert "<b>" in text  # HTML format
        assert "Alpha" in text
        assert "Beta" in text
        assert "Gamma" in text

    @pytest.mark.asyncio
    async def test_large_price_formatted(self) -> None:
        """Price >= 1000 is formatted with space separator in HTML."""
        results = [self._make_result({"complex_name": "X", "price_eur": 250000})]
        calls = await self._run(results, 1)
        result_msg = [c for c in calls if "X" in c]
        assert "250" in result_msg[0]
        assert "€" in result_msg[0]

    @pytest.mark.asyncio
    async def test_count_header_reflects_total(self) -> None:
        """Header shows total count, not just returned results."""
        results = [self._make_result({"complex_name": "Solo"})]
        calls = await self._run(results, 42)
        header = [c for c in calls if "42" in c]
        assert len(header) == 1

    @pytest.mark.asyncio
    async def test_max_results_capped(self) -> None:
        """format_apartment_list caps displayed results."""
        results = [self._make_result({"complex_name": f"R{i}"}, rid=str(i)) for i in range(7)]
        calls = await self._run(results, 7)
        # format_apartment_list shows all passed results, header reflects total
        result_msg = [c for c in calls if "R0" in c]
        assert len(result_msg) == 1


class TestDemoVoice:
    @pytest.mark.asyncio
    async def test_voice_transcribed_and_searched(self) -> None:
        from telegram_bot.handlers.demo_handler import handle_demo_search_voice

        message = AsyncMock()
        message.voice = AsyncMock()
        message.text = None
        state = AsyncMock()

        with patch("telegram_bot.handlers.demo_handler.transcribe_voice") as mock_stt:
            mock_stt.return_value = "двушка до 100к"
            pipeline = AsyncMock()
            pipeline.extract.return_value = ApartmentSearchFilters(
                hard=HardFilters(rooms=2, max_price_eur=100000),
                meta=ExtractionMeta(source="llm", confidence="HIGH"),
            )
            apartments_service = AsyncMock()
            apartments_service.scroll_with_filters.return_value = ([], 0, None, [])

            await handle_demo_search_voice(
                message,
                state,
                pipeline=pipeline,
                apartments_service=apartments_service,
            )
            mock_stt.assert_awaited_once()
            pipeline.extract.assert_awaited_once_with("двушка до 100к")

    @pytest.mark.asyncio
    async def test_voice_stt_fails_shows_error(self) -> None:
        from telegram_bot.handlers.demo_handler import handle_demo_search_voice

        message = AsyncMock()
        message.voice = AsyncMock()
        state = AsyncMock()

        with patch("telegram_bot.handlers.demo_handler.transcribe_voice") as mock_stt:
            mock_stt.return_value = None
            await handle_demo_search_voice(message, state, pipeline=AsyncMock())
            calls = [c.args[0] for c in message.answer.await_args_list]
            assert any("распознать" in c for c in calls)


class TestDemoApartmentsWithDynamicExamples:
    @pytest.mark.asyncio
    async def test_dynamic_examples_from_service(self) -> None:
        from telegram_bot.handlers.demo_handler import handle_demo_apartments

        callback = AsyncMock()
        callback.answer = AsyncMock()
        callback.message = AsyncMock()
        state = AsyncMock()

        apartments_service = AsyncMock()
        apartments_service.get_collection_stats.return_value = {
            "cities": ["Солнечный берег", "Свети Влас", "Элените"],
            "complexes": ["Premier Fort Beach"],
            "rooms": [1, 2, 3],
            "min_price": 69500,
            "max_price": 314000,
        }
        await handle_demo_apartments(callback, state, apartments_service=apartments_service)
        state.update_data.assert_awaited_once()
        saved = state.update_data.await_args.kwargs.get("examples")
        assert saved is not None
        assert len(saved) == 4
        assert any("Солнечный берег" in e or "Premier Fort" in e for e in saved)

    @pytest.mark.asyncio
    async def test_dynamic_examples_fallback_on_error(self) -> None:
        from telegram_bot.handlers.demo_handler import handle_demo_apartments
        from telegram_bot.keyboards.demo_keyboard import DEFAULT_EXAMPLES

        callback = AsyncMock()
        callback.answer = AsyncMock()
        callback.message = AsyncMock()
        state = AsyncMock()

        apartments_service = AsyncMock()
        apartments_service.get_collection_stats.side_effect = RuntimeError("Qdrant down")
        await handle_demo_apartments(callback, state, apartments_service=apartments_service)
        saved = state.update_data.await_args.kwargs.get("examples")
        assert saved == DEFAULT_EXAMPLES


class TestKwargsPassthrough:
    """Handlers must accept extra kwargs from aiogram DI (user_service, etc.)."""

    @pytest.mark.asyncio
    async def test_demo_search_text_accepts_extra_kwargs(self) -> None:
        """handle_demo_search_text forwards unknown DI kwargs to _run_demo_search."""
        message = AsyncMock()
        message.text = "студия"
        state = AsyncMock()
        pipeline = AsyncMock()
        pipeline.extract.return_value = ApartmentSearchFilters(
            hard=HardFilters(rooms=1),
            meta=ExtractionMeta(source="llm", confidence="MEDIUM"),
        )
        apartments_service = AsyncMock()
        apartments_service.scroll_with_filters.return_value = ([], 0, None, [])

        # aiogram DI injects extra services; must not raise TypeError
        await handle_demo_search_text(
            message,
            state,
            pipeline=pipeline,
            apartments_service=apartments_service,
            user_service=AsyncMock(),
            i18n=AsyncMock(),
        )
        pipeline.extract.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_demo_voice_accepts_extra_kwargs(self) -> None:
        """handle_demo_search_voice forwards unknown DI kwargs without error."""
        from telegram_bot.handlers.demo_handler import handle_demo_search_voice

        message = AsyncMock()
        message.voice = AsyncMock()
        state = AsyncMock()

        with patch("telegram_bot.handlers.demo_handler.transcribe_voice") as mock_stt:
            mock_stt.return_value = "студия"
            pipeline = AsyncMock()
            pipeline.extract.return_value = ApartmentSearchFilters(
                hard=HardFilters(rooms=1),
                meta=ExtractionMeta(source="llm", confidence="MEDIUM"),
            )
            apartments_service = AsyncMock()
            apartments_service.scroll_with_filters.return_value = ([], 0, None, [])

            await handle_demo_search_voice(
                message,
                state,
                pipeline=pipeline,
                apartments_service=apartments_service,
                user_service=AsyncMock(),
            )
            pipeline.extract.assert_awaited_once()


class TestDemoSearchObservability:
    def test_run_demo_search_is_observed(self) -> None:
        """_run_demo_search must be @observe-decorated (span: demo-search)."""
        from telegram_bot.handlers.demo_handler import _run_demo_search

        assert hasattr(_run_demo_search, "__wrapped__"), (
            "_run_demo_search must be decorated with @observe(name='demo-search')"
        )
