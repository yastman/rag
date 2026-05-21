"""Contract tests for Issue #1238: prefer aiogram InlineKeyboardBuilder.

The SDK registry rule is: "НЕ писать кастомные InlineKeyboard для навигации
— использовать Select/Button/SwitchTo / InlineKeyboardBuilder".

These tests enforce the migration target in two static-keyboard modules:
  - telegram_bot/feedback.py
  - telegram_bot/keyboards/services_keyboard.py

Behavioural contracts (button counts, callback_data, labels) are already
covered by tests/unit/test_feedback.py and tests/unit/test_feedback_handler.py.
This file only enforces the *implementation pattern* — that the modules use
InlineKeyboardBuilder and never construct ``InlineKeyboardMarkup`` manually
with the ``inline_keyboard=`` kwarg.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


SOURCES = {
    "feedback": Path("telegram_bot/feedback.py"),
    "services_keyboard": Path("telegram_bot/keyboards/services_keyboard.py"),
}


def _module_source(key: str) -> str:
    path = SOURCES[key]
    assert path.exists(), f"Expected source file {path} to exist"
    return path.read_text(encoding="utf-8")


def _module_ast(key: str) -> ast.Module:
    return ast.parse(_module_source(key))


# ---------------------------------------------------------------------------
# Import contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("module", ["feedback", "services_keyboard"])
def test_module_imports_inline_keyboard_builder(module: str) -> None:
    """Each migrated module must import ``InlineKeyboardBuilder``."""
    tree = _module_ast(module)
    found = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "aiogram.utils.keyboard":
            for alias in node.names:
                if alias.name == "InlineKeyboardBuilder":
                    found = True
                    break
        if found:
            break
    assert found, (
        f"telegram_bot/{SOURCES[module]} must import InlineKeyboardBuilder from "
        f"aiogram.utils.keyboard (issue #1238 SDK convention)."
    )


# ---------------------------------------------------------------------------
# Construction contract — no manual InlineKeyboardMarkup(inline_keyboard=...)
# ---------------------------------------------------------------------------


def _calls_inline_keyboard_markup_with_kwarg(tree: ast.Module) -> list[ast.Call]:
    """Find ``InlineKeyboardMarkup(inline_keyboard=...)`` constructor calls.

    The migration replaces these with ``builder.as_markup()``. A bare
    ``InlineKeyboardMarkup`` reference (e.g. as a return-type annotation) is
    still allowed and not flagged here.
    """
    offending: list[ast.Call] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match both `InlineKeyboardMarkup(...)` and `aiogram.types.InlineKeyboardMarkup(...)`.
        is_markup_ctor = (isinstance(func, ast.Name) and func.id == "InlineKeyboardMarkup") or (
            isinstance(func, ast.Attribute) and func.attr == "InlineKeyboardMarkup"
        )
        if not is_markup_ctor:
            continue
        # Only flag the manual construction pattern that #1238 wants gone.
        if any(kw.arg == "inline_keyboard" for kw in node.keywords):
            offending.append(node)
    return offending


@pytest.mark.parametrize("module", ["feedback", "services_keyboard"])
def test_module_uses_builder_not_manual_markup(module: str) -> None:
    """No manual ``InlineKeyboardMarkup(inline_keyboard=...)`` constructions."""
    tree = _module_ast(module)
    offending = _calls_inline_keyboard_markup_with_kwarg(tree)
    if offending:
        locations = ", ".join(f"line {call.lineno}" for call in offending)
        pytest.fail(
            f"telegram_bot/{SOURCES[module]} still constructs InlineKeyboardMarkup "
            f"manually at {locations}. Issue #1238 requires using "
            f"InlineKeyboardBuilder().as_markup() instead."
        )


@pytest.mark.parametrize("module", ["feedback", "services_keyboard"])
def test_module_invokes_builder(module: str) -> None:
    """At least one ``InlineKeyboardBuilder()`` instantiation must be present."""
    tree = _module_ast(module)
    found = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "InlineKeyboardBuilder"
        ):
            found = True
            break
    assert found, (
        f"telegram_bot/{SOURCES[module]} must instantiate InlineKeyboardBuilder() at "
        f"least once after the issue #1238 migration."
    )


@pytest.mark.parametrize("module", ["feedback", "services_keyboard"])
def test_module_calls_as_markup(module: str) -> None:
    """Builders must be finalized via ``.as_markup()`` so the public API stays
    ``InlineKeyboardMarkup`` for callers."""
    src = _module_source(module)
    assert ".as_markup()" in src, (
        f"telegram_bot/{SOURCES[module]} must call ``.as_markup()`` to finalize "
        f"its InlineKeyboardBuilder (issue #1238)."
    )
