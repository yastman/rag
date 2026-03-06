"""Inline keyboards for demo flow."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def build_demo_menu() -> InlineKeyboardMarkup:
    """Main demo menu with feature buttons."""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏖 Подбор апартаментов", callback_data="demo:apartments")
    builder.adjust(1)
    return builder.as_markup()


def build_demo_examples(examples: list[str]) -> InlineKeyboardMarkup:
    """Example query buttons for apartment search."""
    builder = InlineKeyboardBuilder()
    for i, ex in enumerate(examples):
        builder.button(text=ex, callback_data=f"demo:example:{i}")
    builder.adjust(1)
    return builder.as_markup()


DEFAULT_EXAMPLES = [
    "Студия в Солнечном берегу до 100 000€",
    "Двушка в Premier Fort Beach",
    "Трёшка в Элените до 200 000€",
    "Апартамент в Свети Влас от 150 000€",
]
