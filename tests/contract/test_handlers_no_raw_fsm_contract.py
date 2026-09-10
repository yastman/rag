"""Contract: every FSM ``StatesGroup`` is owned by a registered dialog (#3390).

Each declared group in ``telegram_bot/dialogs/states.py`` must be referenced by a
dialog module that ``lifecycle.setup_dialogs`` registers — delete unwired groups,
don't archive them. Behavior transitions are owned by the tests/unit/dialogs suites.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


TG = Path(__file__).resolve().parents[2] / "telegram_bot"


def _declared_groups() -> list[str]:
    """StatesGroup class names declared in ``telegram_bot/dialogs/states.py``."""
    tree = ast.parse((TG / "dialogs" / "states.py").read_text(encoding="utf-8"))
    return sorted(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and any(
            getattr(base, "id", getattr(base, "attr", "")) == "StatesGroup" for base in node.bases
        )
    )


def _registered_dialog_sources() -> str:
    """Sources of every ``telegram_bot.dialogs.*`` module ``setup_dialogs`` imports."""
    tree = ast.parse((TG / "lifecycle" / "lifecycle.py").read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "setup_dialogs":
            modules.update(
                sub.module
                for sub in ast.walk(node)
                if isinstance(sub, ast.ImportFrom)
                and sub.module
                and sub.module.startswith("telegram_bot.dialogs")
            )
    parts: list[str] = []
    for module in sorted(modules):
        path = TG / "dialogs" / Path(*module.split(".")[2:])
        files = sorted(path.rglob("*.py")) if path.is_dir() else [path.with_suffix(".py")]
        parts.extend(p.read_text(encoding="utf-8") for p in files)
    return "\n".join(parts)


@pytest.mark.parametrize("group_name", _declared_groups())
def test_states_group_is_wired_by_a_registered_dialog(group_name: str) -> None:
    """Each declared StatesGroup must be referenced by a registered dialog (#3390)."""
    assert group_name in _registered_dialog_sources(), (
        f"{group_name!r} is declared in telegram_bot/dialogs/states.py but is "
        "not referenced by any dialog module registered in lifecycle.setup_dialogs. "
        "Wire it into a registered dialog or delete it (issue #3390)."
    )
