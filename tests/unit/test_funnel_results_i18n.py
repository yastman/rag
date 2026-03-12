"""Tests for i18n in funnel results: get_results_data and on_results_browse (#935)."""

from __future__ import annotations

import pytest


pytest.importorskip("aiogram", reason="aiogram not installed")

from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# get_results_data
# ---------------------------------------------------------------------------


async def test_get_results_data_uses_i18n_when_available() -> None:
    """get_results_data uses i18n.get() for results text when i18n is injected."""
    from telegram_bot.dialogs.funnel import get_results_data

    mock_i18n = MagicMock()
    mock_i18n.get = MagicMock(side_effect=lambda key, **_kw: f"[{key}]")

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {
        "_search_results": [{"id": "1"}],
        "_search_total": 5,
    }

    result = await get_results_data(i18n=mock_i18n, dialog_manager=dialog_manager)

    assert result["results_text"] == "[funnel-results-choose-format]"
    assert result["btn_back"] == "[results-refine]"
    assert result["has_results"] is True


async def test_get_results_data_no_results_uses_i18n() -> None:
    """get_results_data uses i18n for no-results message."""
    from telegram_bot.dialogs.funnel import get_results_data

    mock_i18n = MagicMock()
    mock_i18n.get = MagicMock(side_effect=lambda key, **_kw: f"[{key}]")

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {
        "_search_results": [],
        "_search_total": 0,
    }

    result = await get_results_data(i18n=mock_i18n, dialog_manager=dialog_manager)

    assert result["results_text"] == "[results-no-results]"
    assert result["has_results"] is False


async def test_get_results_data_falls_back_without_i18n() -> None:
    """get_results_data falls back to Russian when i18n is None."""
    from telegram_bot.dialogs.funnel import get_results_data

    dialog_manager = MagicMock()
    dialog_manager.dialog_data = {
        "_search_results": [{"id": "1"}],
        "_search_total": 3,
    }

    result = await get_results_data(i18n=None, dialog_manager=dialog_manager)

    assert "3" in result["results_text"]
    assert "Найдено" in result["results_text"]


# ---------------------------------------------------------------------------
# on_results_browse
# ---------------------------------------------------------------------------


def _make_manager(results: list, total: int, i18n: MagicMock | None = None) -> MagicMock:
    """Create a mock DialogManager with dialog_data and middleware_data."""
    manager = MagicMock()
    manager.dialog_data = {
        "_search_results": results,
        "_search_total": total,
        "_search_next_start": None,
        "_search_page_ids": None,
        "_search_filters": {},
    }
    manager.middleware_data = {
        "i18n": i18n,
        "state": None,
        "property_bot": None,
    }
    manager.done = AsyncMock()
    return manager


async def test_on_results_browse_no_results_uses_i18n() -> None:
    """on_results_browse sends i18n no-results message when results are empty."""
    from telegram_bot.dialogs.funnel import on_results_browse

    mock_i18n = MagicMock()
    mock_i18n.get = MagicMock(side_effect=lambda key, **_kw: f"[{key}]")

    manager = _make_manager(results=[], total=0, i18n=mock_i18n)

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()

    button = MagicMock()
    button.widget_id = "results_cards"

    with patch("telegram_bot.keyboards.client_keyboard.build_catalog_keyboard"):
        await on_results_browse(callback, button, manager)

    callback.message.answer.assert_awaited_once()
    text = callback.message.answer.call_args.args[0]
    assert text == "[results-no-results]"


async def test_on_results_browse_cards_uses_i18n_shown() -> None:
    """on_results_browse uses i18n results-shown for card view footer."""
    from telegram_bot.dialogs.funnel import on_results_browse

    mock_i18n = MagicMock()
    mock_i18n.get = MagicMock(side_effect=lambda key, **_kw: f"[{key}]")

    results = [{"id": "1"}, {"id": "2"}]
    manager = _make_manager(results=results, total=5, i18n=mock_i18n)

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()
    callback.from_user = MagicMock(id=123)

    button = MagicMock()
    button.widget_id = "results_cards"

    mock_kb = MagicMock()

    with patch(
        "telegram_bot.keyboards.client_keyboard.build_catalog_keyboard", return_value=mock_kb
    ):
        await on_results_browse(callback, button, manager)

    # Last call should be the "shown" message
    last_call = callback.message.answer.call_args_list[-1]
    assert last_call.args[0] == "[results-shown]"


async def test_on_results_browse_no_i18n_falls_back() -> None:
    """on_results_browse falls back to Russian without i18n."""
    from telegram_bot.dialogs.funnel import on_results_browse

    manager = _make_manager(results=[], total=0, i18n=None)

    callback = MagicMock()
    callback.message = MagicMock()
    callback.message.answer = AsyncMock()

    button = MagicMock()
    button.widget_id = "results_cards"

    with patch("telegram_bot.keyboards.client_keyboard.build_catalog_keyboard"):
        await on_results_browse(callback, button, manager)

    text = callback.message.answer.call_args.args[0]
    assert "критериям" in text
