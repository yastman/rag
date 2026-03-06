"""E2E test for full demo flow: button → examples → search."""

import pytest

from telegram_bot.handlers.demo_handler import DemoStates
from telegram_bot.keyboards.client_keyboard import MENU_BUTTONS
from telegram_bot.keyboards.demo_keyboard import (
    DEFAULT_EXAMPLES,
    build_demo_examples,
    build_demo_menu,
)
from telegram_bot.services.apartment_extraction_pipeline import ApartmentExtractionPipeline
from telegram_bot.services.apartment_filter_extractor import ApartmentFilterExtractor


def test_demo_button_exists_in_menu():
    assert "demo" in MENU_BUTTONS.values()


def test_demo_menu_has_apartments_button():
    kb = build_demo_menu()
    texts = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "🏖 Подбор апартаментов" in texts


def test_demo_examples_keyboard():
    kb = build_demo_examples(DEFAULT_EXAMPLES)
    assert len(kb.inline_keyboard) == 4


def test_demo_states_defined():
    assert DemoStates.waiting_query is not None


@pytest.mark.asyncio
async def test_pipeline_regex_fallback_works():
    """Without LLM, pipeline falls back to regex."""
    pipe = ApartmentExtractionPipeline(regex_extractor=ApartmentFilterExtractor())
    result = await pipe.extract("двушка до 100000")
    assert result.hard.rooms == 2
    assert result.meta.source == "regex"
