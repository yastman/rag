"""Demo flow handler — FSM-based apartment search with LLM extraction."""

from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from telegram_bot.callback_data import DemoCB
from telegram_bot.keyboards.demo_keyboard import (
    DEFAULT_EXAMPLES,
    build_demo_examples,
    build_demo_menu,
)


logger = logging.getLogger(__name__)


class DemoStates(StatesGroup):
    waiting_query = State()


async def handle_demo_button(message: Message) -> None:
    """Handle '🎯 Демонстрация' button press."""
    await message.answer(
        "🎯 Демонстрация возможностей\n\nПосмотрите, как работает умный подбор недвижимости:",
        reply_markup=build_demo_menu(),
    )


async def handle_demo_apartments(
    callback: CallbackQuery,
    state: FSMContext,
    apartments_service: Any = None,
) -> None:
    """Show instruction + example buttons, set FSM state."""
    await callback.answer()
    await state.set_state(DemoStates.waiting_query)

    examples = DEFAULT_EXAMPLES
    if apartments_service is not None:
        try:
            from telegram_bot.services.apartments_service import generate_search_examples

            stats = await apartments_service.get_collection_stats()
            examples = generate_search_examples(stats)
        except Exception:
            logger.warning("Failed to get dynamic examples, using defaults", exc_info=True)

    await state.update_data(examples=examples)

    await callback.message.answer(
        "🏖 Подбор апартаментов\n\n"
        "Напишите текстом или отправьте голосовое сообщение.\n"
        "Или выберите пример:",
        reply_markup=build_demo_examples(examples),
    )


async def handle_demo_example(
    callback: CallbackQuery,
    callback_data: DemoCB | None = None,
    state: FSMContext | None = None,
    pipeline: Any = None,
    apartments_service: Any = None,
    embeddings: Any = None,
) -> None:
    """Handle example button click — treat as text query."""
    await callback.answer()
    if state is None and callback_data is not None and hasattr(callback_data, "get_data"):
        # Backward-compatible direct calls: handle_demo_example(callback, state, ...)
        state = callback_data  # type: ignore[assignment]
        callback_data = None
    if state is None:
        return

    idx: int | None = callback_data.idx if callback_data is not None else None
    if idx is None:
        raw_data = callback.data or ""
        if raw_data.startswith("demo:example:"):
            try:
                idx = int(raw_data.rsplit(":", 1)[-1])
            except ValueError:
                return
        else:
            return

    data = await state.get_data()
    examples = data.get("examples", DEFAULT_EXAMPLES)
    if idx >= len(examples):
        return
    query = examples[idx]
    if callback.message is None:
        return

    await _run_demo_search(
        query,
        callback.message,  # type: ignore[arg-type]
        state,
        pipeline=pipeline,
        apartments_service=apartments_service,
        embeddings=embeddings,
    )


async def handle_demo_search_text(
    message: Message,
    state: FSMContext,
    pipeline: Any = None,
    apartments_service: Any = None,
    embeddings: Any = None,
    **kwargs: Any,
) -> None:
    """Handle text input in demo mode — LLM extraction → search → results."""
    if not message.text:
        await message.answer("Отправьте текстовое или голосовое сообщение.")
        return
    await _run_demo_search(
        message.text,
        message,
        state,
        pipeline=pipeline,
        apartments_service=apartments_service,
        embeddings=embeddings,
        **kwargs,
    )


async def _run_demo_search(
    query: str,
    message: Message,
    state: FSMContext,
    pipeline: Any = None,
    apartments_service: Any = None,
    embeddings: Any = None,
    **kwargs: Any,
) -> None:
    """Core search logic: LLM extraction → Qdrant → format results."""
    if not pipeline:
        await message.answer("Сервис поиска временно недоступен.")
        return

    await message.answer("🔍 Ищу подходящие варианты...")

    # 1. LLM extraction
    extraction = await pipeline.extract(query)

    if not apartments_service or not embeddings:
        await message.answer(
            f"📋 Распознано: {extraction.hard.model_dump(exclude_none=True)}\n"
            "(поиск недоступен в тестовом режиме)"
        )
        return

    # 2. Embeddings
    semantic_query = extraction.meta.semantic_remainder or query
    dense, sparse, colbert = await embeddings.aembed_hybrid_with_colbert(semantic_query)

    # 3. Search
    filters = extraction.hard.to_filters_dict()
    results, count = await apartments_service.search_with_filters(
        dense_vector=dense,
        colbert_query=colbert or None,
        sparse_vector=sparse,
        filters=filters or None,
        top_k=5,
    )

    # 4. Format results
    if not results:
        await message.answer(
            "К сожалению, ничего не найдено по вашему запросу.\n"
            "Попробуйте изменить параметры или напишите другой запрос."
        )
        return

    text_parts = [f"Найдено {count} вариантов:\n"]
    for i, r in enumerate(results[:5], 1):
        p = r.get("payload", {})
        name = p.get("complex_name", "—")
        rooms = p.get("rooms", "?")
        price = p.get("price_eur", 0)
        area = p.get("area_m2", 0)
        city = p.get("city", "")
        text_parts.append(f"{i}. **{name}** — {rooms} комн., {area:.0f} м², {price:,.0f}€, {city}")

    await message.answer("\n".join(text_parts), parse_mode="Markdown")


async def handle_demo_search_voice(
    message: Message,
    state: FSMContext,
    pipeline: Any = None,
    apartments_service: Any = None,
    embeddings: Any = None,
    llm: Any = None,
    **kwargs: Any,
) -> None:
    """Handle voice input — STT → LLM extraction → search."""
    await message.answer("🎤 Распознаю голос...")

    text = await transcribe_voice(message, llm=llm)
    if not text:
        await message.answer("Не удалось распознать речь. Попробуйте ещё раз.")
        return

    await message.answer(f"📝 Распознано: {text}")

    await _run_demo_search(
        text,
        message,
        state,
        pipeline=pipeline,
        apartments_service=apartments_service,
        embeddings=embeddings,
        **kwargs,
    )


async def transcribe_voice(message: Message, *, llm: Any = None) -> str | None:
    """Download voice and transcribe via Whisper."""
    import io

    bot = message.bot
    if bot is None or message.voice is None:
        return None
    file = await bot.get_file(message.voice.file_id)
    data = io.BytesIO()
    await bot.download_file(file.file_path, data)  # type: ignore[arg-type]
    data.seek(0)
    data.name = "voice.ogg"  # type: ignore[attr-defined]

    if llm is None:
        from langfuse.openai import AsyncOpenAI

        llm = AsyncOpenAI()

    transcript = await llm.audio.transcriptions.create(
        model="whisper",
        file=data,
        language="ru",
    )
    return transcript.text or None


def create_demo_router() -> Router:
    """Create a fresh demo router instance for each bot instance."""
    router = Router(name="demo")
    router.callback_query.register(
        handle_demo_apartments,
        DemoCB.filter(F.action == "apartments"),
    )
    router.callback_query.register(
        handle_demo_example,
        DemoCB.filter(F.action == "example"),
    )
    router.message.register(handle_demo_search_voice, DemoStates.waiting_query, F.voice)
    router.message.register(handle_demo_search_text, DemoStates.waiting_query, F.text)
    return router
