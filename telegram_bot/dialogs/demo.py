"""Demo apartment search dialog — aiogram-dialog scaffold (#907)."""

from __future__ import annotations

import logging
import operator
from typing import Any

from aiogram.enums import ContentType
from aiogram.types import CallbackQuery, Message
from aiogram_dialog import Dialog, DialogManager, Window
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog.widgets.kbd import Button, Column, Select
from aiogram_dialog.widgets.text import Format

from telegram_bot.dialogs.states import CatalogBrowsingSG, DemoSG
from telegram_bot.handlers.demo_handler import transcribe_voice
from telegram_bot.keyboards.demo_keyboard import DEFAULT_EXAMPLES


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Getters
# ---------------------------------------------------------------------------


async def intro_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Return example queries for the intro window."""
    apartments_service = dialog_manager.middleware_data.get("apartments_service")
    examples = DEFAULT_EXAMPLES

    if apartments_service is not None:
        try:
            from telegram_bot.services.apartments_service import generate_search_examples

            stats = await apartments_service.get_collection_stats()
            examples = generate_search_examples(stats)
        except Exception:
            logger.warning(
                "Failed to get dynamic examples in demo dialog, using defaults", exc_info=True
            )

    return {
        "prompt": (
            "🏖 Подбор апартаментов\n\n"
            "Напишите текстом или отправьте голосовое сообщение.\n"
            "Или выберите пример:"
        ),
        "examples": examples,
    }


async def results_getter(dialog_manager: DialogManager, **kwargs: Any) -> dict[str, Any]:
    """Format search results from dialog_data for display."""
    dialog_data = dialog_manager.dialog_data
    degraded_text: str | None = dialog_data.get("degraded_text")

    if degraded_text:
        return {
            "results_text": degraded_text,
            "count": 0,
            "query": dialog_data.get("query", ""),
        }

    results: list[dict[str, Any]] = dialog_data.get("results", [])
    count: int = dialog_data.get("count", 0)
    query: str = dialog_data.get("query", "")

    if not results:
        return {
            "results_text": (
                "К сожалению, ничего не найдено по вашему запросу.\n"
                "Попробуйте изменить параметры или напишите другой запрос."
            ),
            "count": 0,
            "query": query,
        }

    text_parts = [f"Найдено {count} вариантов:\n"]
    for i, r in enumerate(results[:5], 1):
        p = r.get("payload", {})
        name = p.get("complex_name", "—")
        rooms = p.get("rooms", "?")
        price = p.get("price_eur", 0)
        area = p.get("area_m2", 0)
        city = p.get("city", "")
        text_parts.append(f"{i}. {name} — {rooms} комн., {area:.0f} м², {price:,.0f}€, {city}")

    return {
        "results_text": "\n".join(text_parts),
        "count": count,
        "query": query,
    }


# ---------------------------------------------------------------------------
# Core search (stores results in dialog_data, then switches state)
# ---------------------------------------------------------------------------


async def _dialog_search(query: str, message: Message, manager: DialogManager) -> None:
    """LLM extraction → scroll_with_filters → catalog browsing mode."""
    from aiogram.fsm.context import FSMContext

    pipeline = manager.middleware_data.get("pipeline")
    apartments_service = manager.middleware_data.get("apartments_service")
    state: FSMContext | None = manager.middleware_data.get("state")

    if not pipeline:
        await message.answer("Сервис поиска временно недоступен.")
        return

    await message.answer("🔍 Ищу подходящие варианты...")

    extraction = await pipeline.extract(query)

    if not apartments_service:
        manager.dialog_data["results"] = []
        manager.dialog_data["count"] = 0
        manager.dialog_data["query"] = query
        manager.dialog_data["degraded_text"] = (
            f"📋 Распознано: {extraction.hard.model_dump(exclude_none=True)}\n"
            "(поиск недоступен в тестовом режиме)"
        )
        await manager.switch_to(DemoSG.results)
        return

    # Build filters from extraction
    filters = extraction.hard.to_filters_dict() or None

    # Scroll (payload-only, sorted by price)
    _PAGE_SIZE = 10
    results, total_count, next_start, page_ids = await apartments_service.scroll_with_filters(
        filters=filters,
        limit=_PAGE_SIZE,
    )

    if not results:
        await message.answer(
            "К сожалению, ничего не найдено по вашему запросу.\n"
            "Попробуйте изменить параметры или напишите другой запрос."
        )
        return

    from telegram_bot.dialogs.funnel import format_apartment_list
    from telegram_bot.keyboards.client_keyboard import build_catalog_keyboard

    text = format_apartment_list(results, shown_start=1, total=total_count)
    catalog_kb = build_catalog_keyboard(shown=len(results), total=total_count)
    await message.answer(text, parse_mode="HTML", reply_markup=catalog_kb)

    # Transition to CatalogBrowsingSG.browsing
    if state is not None:
        await state.set_state(CatalogBrowsingSG.browsing)
        await state.update_data(
            apartment_filters=filters if isinstance(filters, dict) else {},
            apartment_offset=len(results),
            apartment_total=total_count,
            apartment_next_offset=next_start,
            apartment_scroll_seen_ids=page_ids,
            apartment_query=query,
        )

    # Close demo dialog
    await manager.done()


# ---------------------------------------------------------------------------
# Input handlers
# ---------------------------------------------------------------------------


async def on_text_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Handle text message in intro window — run apartment search."""
    if not message.text:
        return
    await _dialog_search(message.text, message, manager)


async def on_voice_input(message: Message, widget: MessageInput, manager: DialogManager) -> None:
    """Handle voice message in intro window — STT then apartment search."""
    await message.answer("🎤 Распознаю голос...")
    text = await transcribe_voice(message)
    if not text:
        await message.answer("Не удалось распознать речь. Попробуйте ещё раз.")
        return
    await message.answer(f"📝 Распознано: {text}")
    await _dialog_search(text, message, manager)


async def on_example_selected(
    callback: CallbackQuery,
    widget: Any,
    manager: DialogManager,
    item_id: str,
) -> None:
    """Handle example button click — run search with selected example text."""
    if callback.message is None:
        return
    await _dialog_search(item_id, callback.message, manager)  # type: ignore[arg-type]


async def on_new_search(
    callback: CallbackQuery,
    button: Any,
    manager: DialogManager,
) -> None:
    """Return to intro window for a new query."""
    await manager.switch_to(DemoSG.intro)


# ---------------------------------------------------------------------------
# Dialog definition
# ---------------------------------------------------------------------------


demo_dialog = Dialog(
    # Window 1: query input
    Window(
        Format("{prompt}"),
        Column(
            Select(
                Format("{item}"),
                id="s_example",
                item_id_getter=operator.itemgetter(0),
                items="examples",
                on_click=on_example_selected,
            ),
        ),
        MessageInput(on_text_input, content_types=[ContentType.TEXT]),
        MessageInput(on_voice_input, content_types=[ContentType.VOICE]),
        getter=intro_getter,
        state=DemoSG.intro,
    ),
    # Window 2: results display
    Window(
        Format("{results_text}"),
        Button(Format("🔍 Новый запрос"), id="new_search", on_click=on_new_search),
        getter=results_getter,
        state=DemoSG.results,
    ),
)
