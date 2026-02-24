# tests/unit/keyboards/test_property_card.py
"""Tests for property card rendering."""

from telegram_bot.keyboards.property_card import (
    build_card_buttons,
    build_results_footer,
    format_property_card,
)


def test_format_property_card():
    card = format_property_card(
        property_id="p1",
        complex_name="Sunrise Complex",
        location="Солнечный Берег",
        property_type="Студия",
        floor=2,
        area_m2=42,
        view="Бассейн",
        price_eur=48500,
    )
    assert "Sunrise Complex" in card
    assert "48 500 €" in card
    assert "Студия" in card


def test_build_card_buttons():
    from aiogram.types import InlineKeyboardMarkup

    kb = build_card_buttons(property_id="p1")
    assert isinstance(kb, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "fav:add:p1" in callbacks


def test_build_results_footer():
    from aiogram.types import InlineKeyboardMarkup

    kb = build_results_footer(shown=5, total=23, has_more=True)
    assert isinstance(kb, InlineKeyboardMarkup)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "results:more" in callbacks
    assert "results:refine" in callbacks
    assert "results:viewing" in callbacks
