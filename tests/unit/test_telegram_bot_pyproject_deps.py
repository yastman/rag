"""Regression checks for telegram_bot package runtime dependencies."""

from pathlib import Path


def test_telegram_bot_pyproject_includes_aiogram_dialog_dependency() -> None:
    text = Path("telegram_bot/pyproject.toml").read_text(encoding="utf-8")
    assert "aiogram-dialog" in text


def test_telegram_bot_pyproject_includes_asyncpg_dependency() -> None:
    text = Path("telegram_bot/pyproject.toml").read_text(encoding="utf-8")
    assert "asyncpg" in text


def test_telegram_bot_pyproject_includes_apscheduler_dependency() -> None:
    text = Path("telegram_bot/pyproject.toml").read_text(encoding="utf-8")
    assert "apscheduler" in text
