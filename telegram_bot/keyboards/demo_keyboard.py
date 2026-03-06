"""Inline keyboards for demo flow."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def build_demo_menu() -> InlineKeyboardMarkup:
    """Main demo menu with feature buttons."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏖 Подбор апартаментов", callback_data="demo:apartments")],
        ]
    )


def build_demo_examples(examples: list[str]) -> InlineKeyboardMarkup:
    """Example query buttons for apartment search."""
    buttons = [
        [InlineKeyboardButton(text=ex, callback_data=f"demo:example:{i}")]
        for i, ex in enumerate(examples)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


DEFAULT_EXAMPLES = [
    "Студия в Солнечном берегу до 100 000€",
    "Двушка в Premier Fort Beach",
    "Трёшка в Элените до 200 000€",
    "Апартамент в Свети Влас от 150 000€",
]
