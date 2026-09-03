"""Tests for the catalog state owner and reply-keyboard routing."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from telegram_bot.dialogs.states import CatalogSG, FilterSG


def test_catalog_dialog_has_results_window() -> None:
    from telegram_bot.dialogs.catalog import catalog_dialog

    assert CatalogSG.results in catalog_dialog.windows


def test_catalog_results_window_has_no_inline_control_buttons() -> None:
    from telegram_bot.dialogs.catalog import catalog_dialog

    window = catalog_dialog.windows[CatalogSG.results]
    widget_ids = {getattr(widget, "widget_id", None) for widget in window.keyboard.buttons}
    assert "catalog_more" not in widget_ids
    assert "catalog_filters" not in widget_ids
    assert "catalog_home" not in widget_ids


def test_catalog_results_window_keeps_message_input() -> None:
    from aiogram_dialog.widgets.input import MessageInput

    from telegram_bot.dialogs.catalog import catalog_dialog

    window = catalog_dialog.windows[CatalogSG.results]
    assert any(isinstance(widget, MessageInput) for widget in window.on_message.inputs)


@pytest.mark.asyncio
async def test_catalog_home_restores_client_reply_keyboard() -> None:
    from telegram_bot.dialogs.catalog import on_catalog_home

    manager = AsyncMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    manager.middleware_data = {"state": state, "i18n": None}
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.message.chat = MagicMock(id=456)
    callback.message.bot = MagicMock(delete_message=AsyncMock())
    callback.message.from_user = MagicMock(first_name="Test")

    await on_catalog_home(callback, MagicMock(), manager)

    state.clear.assert_awaited_once()
    manager.reset_stack.assert_awaited_once_with(remove_keyboard=True)
    callback.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_catalog_filters_starts_filter_dialog_with_current_filters() -> None:
    from aiogram_dialog import ShowMode, StartMode

    from telegram_bot.dialogs.catalog import on_catalog_filters

    state = AsyncMock()
    state.get_data.return_value = {"catalog_runtime": {"filters": {"city": "Варна"}}}
    manager = AsyncMock()
    manager.middleware_data = {"state": state}
    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock(return_value=MagicMock(delete=AsyncMock()))
    callback.message.chat = MagicMock(id=456)
    callback.message.bot = MagicMock(delete_message=AsyncMock())

    await on_catalog_filters(callback, MagicMock(), manager)

    callback.message.answer.assert_not_awaited()
    manager.start.assert_awaited_once_with(
        FilterSG.hub,
        data={"filters": {"city": "Варна"}},
        mode=StartMode.RESET_STACK,
        show_mode=ShowMode.SEND,
    )


@pytest.mark.asyncio
async def test_show_catalog_controls_skips_status_message_for_list_mode() -> None:
    from telegram_bot.dialogs.catalog import show_catalog_controls

    manager = AsyncMock()
    state = AsyncMock()
    state.get_data.return_value = {}
    manager.middleware_data = {"state": state, "i18n": None}
    message = MagicMock()
    message.answer = AsyncMock()
    message.chat = MagicMock(id=456)
    message.bot = MagicMock(delete_message=AsyncMock())

    runtime = {
        "view_mode": "list",
        "shown_count": 5,
        "total": 5,
        "query": "funnel:Солнечный берег",
        "source": "funnel",
    }

    updated = await show_catalog_controls(message=message, dialog_manager=manager, runtime=runtime)

    assert updated["view_mode"] == "list"
    message.answer.assert_not_awaited()


# ---------------------------------------------------------------------------
# Catalog voice input — optional adapter with typed fallback (#3240)
# ---------------------------------------------------------------------------


def _voice_ready_config():
    from types import SimpleNamespace

    return SimpleNamespace(
        voice_enabled=True,
        llm_api_key="sk-test",
        stt_model="whisper",
        voice_language="ru",
        voice_timeout=30,
        show_transcription=True,
    )


@pytest.mark.asyncio
async def test_catalog_voice_input_ready_transcribes_and_searches() -> None:
    """Ready voice reuses the demo search path (same catalog contract as text)."""
    from telegram_bot.dialogs.catalog.dialog import on_catalog_voice_input

    message = AsyncMock()
    message.voice = MagicMock(file_id="f1")
    state = AsyncMock()
    manager = MagicMock()
    manager.middleware_data = {
        "state": state,
        "bot_config": _voice_ready_config(),
    }
    manager.dialog_data = {}

    with (
        patch(
            "telegram_bot.dialogs.catalog.dialog.transcribe_voice",
            new_callable=AsyncMock,
            return_value="двушка у моря",
        ),
        patch("telegram_bot.dialogs.catalog.dialog.search_catalog_from_query", new_callable=AsyncMock) as search,
    ):
        await on_catalog_voice_input(message, MagicMock(), manager)

    search.assert_awaited_once_with(
        message=message, dialog_manager=manager, query="двушка у моря"
    )


@pytest.mark.asyncio
async def test_catalog_voice_input_not_ready_directs_to_typed_input() -> None:
    """Unconfigured voice must never attempt STT nor search (#3240)."""
    from types import SimpleNamespace

    from telegram_bot.dialogs.catalog.dialog import on_catalog_voice_input

    message = AsyncMock()
    message.voice = MagicMock(file_id="f1")
    state = AsyncMock()
    manager = MagicMock()
    manager.middleware_data = {
        "state": state,
        "bot_config": SimpleNamespace(voice_enabled=False, llm_api_key="sk-test"),
    }

    with (
        patch(
            "telegram_bot.dialogs.catalog.dialog.transcribe_voice",
            new_callable=AsyncMock,
            return_value="не должно вызываться",
        ) as mock_stt,
        patch("telegram_bot.dialogs.catalog.dialog.search_catalog_from_query", new_callable=AsyncMock) as search,
    ):
        await on_catalog_voice_input(message, MagicMock(), manager)

    mock_stt.assert_not_awaited()
    search.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert "текстом" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_catalog_voice_input_stt_failure_offers_typed_input() -> None:
    """Transcription failure must degrade to a typed-input hint, not block."""
    from telegram_bot.dialogs.catalog.dialog import on_catalog_voice_input

    message = AsyncMock()
    message.voice = MagicMock(file_id="f1")
    state = AsyncMock()
    manager = MagicMock()
    manager.middleware_data = {
        "state": state,
        "bot_config": _voice_ready_config(),
    }

    with (
        patch(
            "telegram_bot.dialogs.catalog.dialog.transcribe_voice",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("telegram_bot.dialogs.catalog.dialog.search_catalog_from_query", new_callable=AsyncMock) as search,
    ):
        await on_catalog_voice_input(message, MagicMock(), manager)

    search.assert_not_awaited()
    last_hint = message.answer.await_args_list[-1].args[0]
    assert "текстом" in last_hint
