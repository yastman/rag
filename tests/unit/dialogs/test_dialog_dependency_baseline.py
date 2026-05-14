"""Dependency contract for dialog migration baseline."""

from importlib.metadata import version


def test_dialog_dependency_baseline() -> None:
    assert version("aiogram") == "3.28.2"
    assert version("aiogram-dialog") == "2.6.0"
