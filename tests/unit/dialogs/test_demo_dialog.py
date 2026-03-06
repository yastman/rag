"""Tests for aiogram-dialog demo dialog — getters and handler logic (#907)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.dialogs.states import DemoSG


# ---------------------------------------------------------------------------
# Dialog structure
# ---------------------------------------------------------------------------


def test_demo_dialog_is_dialog_instance() -> None:
    from aiogram_dialog import Dialog

    from telegram_bot.dialogs.demo import demo_dialog

    assert isinstance(demo_dialog, Dialog)


def test_demo_dialog_has_intro_and_results_windows() -> None:
    from telegram_bot.dialogs.demo import demo_dialog

    states = [w.get_state() for w in demo_dialog.windows.values()]
    assert DemoSG.intro in states
    assert DemoSG.results in states


# ---------------------------------------------------------------------------
# intro_getter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_intro_getter_returns_examples_from_service() -> None:
    from telegram_bot.dialogs.demo import intro_getter

    apartments_service = AsyncMock()
    apartments_service.get_collection_stats.return_value = {
        "cities": ["Солнечный берег", "Свети Влас"],
        "complexes": ["Premier Fort Beach"],
        "rooms": [1, 2, 3],
        "min_price": 69500,
        "max_price": 314000,
    }
    manager = MagicMock()
    manager.middleware_data = {"apartments_service": apartments_service}

    result = await intro_getter(dialog_manager=manager)

    assert "examples" in result
    assert len(result["examples"]) > 0
    assert "prompt" in result


@pytest.mark.asyncio
async def test_intro_getter_falls_back_on_service_error() -> None:
    from telegram_bot.dialogs.demo import intro_getter
    from telegram_bot.keyboards.demo_keyboard import DEFAULT_EXAMPLES

    apartments_service = AsyncMock()
    apartments_service.get_collection_stats.side_effect = RuntimeError("Qdrant down")
    manager = MagicMock()
    manager.middleware_data = {"apartments_service": apartments_service}

    result = await intro_getter(dialog_manager=manager)

    assert result["examples"] == DEFAULT_EXAMPLES


@pytest.mark.asyncio
async def test_intro_getter_no_service_uses_defaults() -> None:
    from telegram_bot.dialogs.demo import intro_getter
    from telegram_bot.keyboards.demo_keyboard import DEFAULT_EXAMPLES

    manager = MagicMock()
    manager.middleware_data = {}

    result = await intro_getter(dialog_manager=manager)

    assert result["examples"] == DEFAULT_EXAMPLES


# ---------------------------------------------------------------------------
# results_getter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_results_getter_formats_found_results() -> None:
    from telegram_bot.dialogs.demo import results_getter

    manager = MagicMock()
    manager.dialog_data = {
        "results": [
            {
                "id": "1",
                "payload": {
                    "complex_name": "Fort Beach",
                    "rooms": 2,
                    "price_eur": 95000,
                    "area_m2": 60,
                    "city": "Солнечный берег",
                },
            }
        ],
        "count": 1,
        "query": "двушка",
        "page": 0,
    }

    result = await results_getter(dialog_manager=manager)

    assert "results_text" in result
    assert "Fort Beach" in result["results_text"]
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_results_getter_shows_not_found_when_empty() -> None:
    from telegram_bot.dialogs.demo import results_getter

    manager = MagicMock()
    manager.dialog_data = {"results": [], "count": 0, "query": "пентхаус", "page": 0}

    result = await results_getter(dialog_manager=manager)

    assert (
        "не найдено" in result["results_text"].lower() or "ничего" in result["results_text"].lower()
    )


@pytest.mark.asyncio
async def test_results_getter_degraded_mode() -> None:
    from telegram_bot.dialogs.demo import results_getter

    manager = MagicMock()
    manager.dialog_data = {
        "results": [],
        "count": 0,
        "query": "двушка",
        "page": 0,
        "degraded_text": "📋 Распознано: rooms=2\n(поиск недоступен в тестовом режиме)",
    }

    result = await results_getter(dialog_manager=manager)

    assert "Распознано" in result["results_text"]


# ---------------------------------------------------------------------------
# on_text_input handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_text_input_calls_pipeline_and_switches_to_results() -> None:
    from telegram_bot.dialogs.demo import on_text_input
    from telegram_bot.services.apartment_models import (
        ApartmentSearchFilters,
        ExtractionMeta,
        HardFilters,
    )

    message = AsyncMock()
    message.text = "двушка до 100к"
    widget = MagicMock()
    manager = MagicMock()
    manager.dialog_data = {}

    pipeline = AsyncMock()
    pipeline.extract.return_value = ApartmentSearchFilters(
        hard=HardFilters(rooms=2, max_price_eur=100000),
        meta=ExtractionMeta(source="llm", confidence="HIGH"),
    )
    apartments_service = AsyncMock()
    apartments_service.search_with_filters.return_value = ([], 0)
    embeddings = AsyncMock()
    embeddings.aembed_hybrid_with_colbert.return_value = ([0.1] * 1024, {}, [])

    manager.middleware_data = {
        "pipeline": pipeline,
        "apartments_service": apartments_service,
        "embeddings": embeddings,
    }
    manager.switch_to = AsyncMock()

    await on_text_input(message, widget, manager)

    pipeline.extract.assert_awaited_once_with("двушка до 100к")
    manager.switch_to.assert_awaited_once_with(DemoSG.results)


@pytest.mark.asyncio
async def test_on_text_input_no_pipeline_shows_error() -> None:
    from telegram_bot.dialogs.demo import on_text_input

    message = AsyncMock()
    message.text = "двушка"
    widget = MagicMock()
    manager = MagicMock()
    manager.dialog_data = {}
    manager.middleware_data = {"pipeline": None}
    manager.switch_to = AsyncMock()

    await on_text_input(message, widget, manager)

    message.answer.assert_awaited()
    manager.switch_to.assert_not_awaited()


# ---------------------------------------------------------------------------
# on_voice_input handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_voice_input_transcribes_then_searches() -> None:
    from telegram_bot.dialogs.demo import on_voice_input
    from telegram_bot.services.apartment_models import (
        ApartmentSearchFilters,
        ExtractionMeta,
        HardFilters,
    )

    message = AsyncMock()
    message.voice = MagicMock()
    widget = MagicMock()
    manager = MagicMock()
    manager.dialog_data = {}

    pipeline = AsyncMock()
    pipeline.extract.return_value = ApartmentSearchFilters(
        hard=HardFilters(rooms=2),
        meta=ExtractionMeta(source="llm", confidence="HIGH"),
    )
    apartments_service = AsyncMock()
    apartments_service.search_with_filters.return_value = ([], 0)
    embeddings = AsyncMock()
    embeddings.aembed_hybrid_with_colbert.return_value = ([0.1] * 1024, {}, [])

    manager.middleware_data = {
        "pipeline": pipeline,
        "apartments_service": apartments_service,
        "embeddings": embeddings,
    }
    manager.switch_to = AsyncMock()

    with patch(
        "telegram_bot.dialogs.demo.transcribe_voice", return_value="двушка до 100к"
    ) as mock_stt:
        await on_voice_input(message, widget, manager)
        mock_stt.assert_awaited_once_with(message)

    pipeline.extract.assert_awaited_once_with("двушка до 100к")
    manager.switch_to.assert_awaited_once_with(DemoSG.results)


@pytest.mark.asyncio
async def test_on_voice_input_failed_stt_shows_error() -> None:
    from telegram_bot.dialogs.demo import on_voice_input

    message = AsyncMock()
    message.voice = MagicMock()
    widget = MagicMock()
    manager = MagicMock()
    manager.dialog_data = {}
    manager.middleware_data = {}
    manager.switch_to = AsyncMock()

    with patch("telegram_bot.dialogs.demo.transcribe_voice", return_value=None):
        await on_voice_input(message, widget, manager)

    message.answer.assert_awaited()
    manager.switch_to.assert_not_awaited()


# ---------------------------------------------------------------------------
# on_example_selected handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_on_example_selected_runs_search() -> None:
    from telegram_bot.dialogs.demo import on_example_selected
    from telegram_bot.services.apartment_models import (
        ApartmentSearchFilters,
        ExtractionMeta,
        HardFilters,
    )

    callback = AsyncMock()
    callback.message = AsyncMock()
    widget = MagicMock()
    manager = MagicMock()
    manager.dialog_data = {}

    pipeline = AsyncMock()
    pipeline.extract.return_value = ApartmentSearchFilters(
        hard=HardFilters(rooms=1),
        meta=ExtractionMeta(source="llm", confidence="HIGH"),
    )
    apartments_service = AsyncMock()
    apartments_service.search_with_filters.return_value = ([], 0)
    embeddings = AsyncMock()
    embeddings.aembed_hybrid_with_colbert.return_value = ([0.1] * 1024, {}, [])

    manager.middleware_data = {
        "pipeline": pipeline,
        "apartments_service": apartments_service,
        "embeddings": embeddings,
    }
    manager.switch_to = AsyncMock()

    await on_example_selected(callback, widget, manager, "Студия в Солнечном берегу до 100 000€")

    pipeline.extract.assert_awaited_once_with("Студия в Солнечном берегу до 100 000€")
    manager.switch_to.assert_awaited_once_with(DemoSG.results)
