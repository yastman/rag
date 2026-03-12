"""Tests for FunnelSG.results state and results window (#935)."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_funnel_sg_has_results_state():
    """FunnelSG must have a results State for the results window."""
    from telegram_bot.dialogs.states import FunnelSG

    assert hasattr(FunnelSG, "results"), "FunnelSG is missing 'results' State"


async def test_get_results_data_with_cached_results():
    """get_results_data returns has_results=True and count text when results cached."""
    from telegram_bot.dialogs.funnel import get_results_data

    dm = MagicMock()
    dm.dialog_data = {
        "_search_results": [{"id": "apt-1"}, {"id": "apt-2"}, {"id": "apt-3"}],
        "_search_total": 25,
    }
    dm.middleware_data = {}

    result = await get_results_data(dialog_manager=dm)
    assert result["has_results"] is True
    assert "25" in result["results_text"]


async def test_get_results_data_empty_results():
    """get_results_data returns has_results=False when no results cached."""
    from telegram_bot.dialogs.funnel import get_results_data

    dm = MagicMock()
    dm.dialog_data = {"_search_results": [], "_search_total": 0}
    dm.middleware_data = {}

    result = await get_results_data(dialog_manager=dm)
    assert result["has_results"] is False


async def test_get_results_data_no_cache_key():
    """get_results_data returns has_results=False when _search_results is absent."""
    from telegram_bot.dialogs.funnel import get_results_data

    dm = MagicMock()
    dm.dialog_data = {}
    dm.middleware_data = {}

    result = await get_results_data(dialog_manager=dm)
    assert result["has_results"] is False
