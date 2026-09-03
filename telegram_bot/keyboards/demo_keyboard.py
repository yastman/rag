"""Inline keyboards for demo flow."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from src.runtime.domain_defaults import GOLDEN_DEMO_QUERIES
from telegram_bot.callback_data import DemoCB


def build_demo_menu() -> InlineKeyboardMarkup:
    """Main demo menu with feature buttons."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏖 Подбор апартаментов", callback_data=DemoCB(action="apartments"))
    builder.adjust(1)
    return builder.as_markup()


def build_demo_examples(examples: list[str]) -> InlineKeyboardMarkup:
    """Example query buttons for apartment search."""
    builder = InlineKeyboardBuilder()
    for i, ex in enumerate(examples):
        builder.button(text=ex, callback_data=DemoCB(action="example", idx=i))
    builder.adjust(1)
    return builder.as_markup()


# Visible fallback examples = the golden demo queries (#3203). Each one is
# guaranteed to return listings from the shipped seed (data/apartments.csv)
# through the production extraction path; locked by the seed-truthfulness test.
DEFAULT_EXAMPLES: list[str] = list(GOLDEN_DEMO_QUERIES)
