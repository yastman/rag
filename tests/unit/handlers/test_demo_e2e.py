"""E2E test for full demo flow: button → examples → search."""

import pytest

from telegram_bot.callback_data import DemoCB
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
    assert result.hard.rooms == 3
    assert result.meta.source == "regex"


# --- CallbackData SDK tests ---


def test_demo_cb_apartments_pack_unpack():
    """DemoCB packs/unpacks 'apartments' action correctly."""
    cb = DemoCB(action="apartments")
    packed = cb.pack()
    assert packed.startswith("demo:")
    unpacked = DemoCB.unpack(packed)
    assert unpacked.action == "apartments"
    assert unpacked.idx == 0


def test_demo_cb_example_pack_unpack():
    """DemoCB packs/unpacks 'example' action with idx."""
    cb = DemoCB(action="example", idx=2)
    packed = cb.pack()
    unpacked = DemoCB.unpack(packed)
    assert unpacked.action == "example"
    assert unpacked.idx == 2


def test_demo_menu_uses_callback_data():
    """Demo menu buttons use DemoCB callback_data, not raw strings."""
    kb = build_demo_menu()
    btn = kb.inline_keyboard[0][0]
    unpacked = DemoCB.unpack(btn.callback_data)
    assert unpacked.action == "apartments"


def test_demo_examples_use_callback_data():
    """Example buttons use DemoCB with idx."""
    kb = build_demo_examples(["Query A", "Query B"])
    for i, row in enumerate(kb.inline_keyboard):
        unpacked = DemoCB.unpack(row[0].callback_data)
        assert unpacked.action == "example"
        assert unpacked.idx == i


def test_demo_cb_filter_matches():
    """DemoCB.filter() creates a valid aiogram filter."""
    filt = DemoCB.filter()
    assert filt is not None
