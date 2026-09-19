"""Shared phone normalization stays transport-free and is consumed by the keyboard."""

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PHONE_KEYBOARD_PATH = REPO_ROOT / "telegram_bot" / "keyboards" / "phone_keyboard.py"
PHONE_UTILS_PATH = REPO_ROOT / "src" / "phone_utils.py"


def test_shared_phone_utils_does_not_import_aiogram() -> None:
    """The shared module must be UI-free so Mini App can import it without
    pulling aiogram keyboard types."""
    src = PHONE_UTILS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("aiogram"), (
                    f"src/phone_utils.py imports {alias.name}; "
                    "shared phone normalization must stay UI-free."
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("aiogram"), (
                f"src/phone_utils.py imports from {mod}; "
                "shared phone normalization must stay UI-free."
            )


def test_phone_keyboard_re_exports_or_uses_shared_module() -> None:
    """``phone_keyboard.py`` must consume the shared module so there is one
    source of truth for the validation/normalization logic.

    Accepts either ``src.phone_utils`` (shim) or the canonical
    ``src.phone_utils`` import — both point to the same implementation.
    """
    tree = ast.parse(PHONE_KEYBOARD_PATH.read_text(encoding="utf-8"))
    used_shared = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "src.phone_utils":
            used_shared = True
            break
    assert used_shared, (
        "telegram_bot/keyboards/phone_keyboard.py must import phone "
        "normalization from src.phone_utils to "
        "keep one source of truth."
    )
