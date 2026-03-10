"""Tests for card action context messages (Task 7, #937)."""

from __future__ import annotations


def test_card_viewing_sends_context_message():
    """format_card_context formats apartment details for action messages."""
    from telegram_bot.keyboards.property_card import format_card_context

    context = format_card_context(
        {
            "complex_name": "Premier Fort Beach",
            "property_type": "1-спальня",
            "price_eur": 85000,
            "apartment_number": "305",
        }
    )
    assert "Premier Fort Beach" in context
    assert "85 000" in context
    assert "305" in context


def test_format_card_context_no_apartment_number():
    """format_card_context works without apartment_number."""
    from telegram_bot.keyboards.property_card import format_card_context

    context = format_card_context(
        {
            "complex_name": "Crown Fort Club",
            "property_type": "Студия",
            "price_eur": 45000,
        }
    )
    assert "Crown Fort Club" in context
    assert "45 000" in context


def test_format_card_context_formats_price_with_spaces():
    """Price formatted with spaces as thousands separator."""
    from telegram_bot.keyboards.property_card import format_card_context

    context = format_card_context({"complex_name": "X", "price_eur": 150000})
    assert "150 000" in context
