"""Dependency contract for dialog migration baseline."""

from importlib.metadata import version


def test_dialog_dependency_baseline() -> None:
    assert version("aiogram") == "3.26.0"
    assert version("aiogram-dialog") == "2.5.0"
