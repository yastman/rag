# tests/contract/test_shared_phone_normalization_contract.py
"""Contract: Mini App phone capture must reuse the shared phonenumbers-based
normalization, not redeclare a digit-count regex.

Closes #1614.

Audit evidence:
- ``mini_app/phone.py`` defined its own ``_PHONE_RE = re.compile(r"^\\+?\\d{7,15}$")``
  validator. That regex accepts impossible numbers like ``+11111111111`` or
  ``0000000`` and never normalizes to E.164. CRM lead quality drops because
  the same Mini App-captured contact can be stored in a different format than
  the bot-side phone collection.
- ``telegram_bot/keyboards/phone_keyboard.py`` already had a
  ``normalize_phone()`` using ``phonenumbers.is_valid_number()`` and E.164
  formatting.

The fix moves ``normalize_phone`` / ``validate_phone`` into a shared non-UI
module (``telegram_bot/phone_utils.py``) and points both consumers there.
This contract pins the result.
"""

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PHONE_KEYBOARD_PATH = REPO_ROOT / "telegram_bot" / "keyboards" / "phone_keyboard.py"
# Canonical home moved to src/phone_utils.py in #1948 to break the reverse
# layering between mini_app and telegram_bot. telegram_bot/phone_utils.py is
# kept as a thin re-export shim for bot internal callers.
PHONE_UTILS_PATH = REPO_ROOT / "src" / "phone_utils.py"
PHONE_UTILS_SHIM_PATH = REPO_ROOT / "telegram_bot" / "phone_utils.py"


def test_shared_phone_utils_module_exists() -> None:
    """A non-UI helper module must exist as the single source of truth."""
    assert PHONE_UTILS_PATH.exists(), (
        f"missing {PHONE_UTILS_PATH} — phone normalization must live in a "
        "non-UI module so Mini App and bot can share it without dragging in "
        "aiogram keyboard imports."
    )
    assert PHONE_UTILS_SHIM_PATH.exists(), (
        f"missing {PHONE_UTILS_SHIM_PATH} — the re-export shim under "
        "telegram_bot/ keeps existing bot internal callers working after the "
        "canonical home moved to src/phone_utils.py (#1948)."
    )


def test_shared_phone_utils_exports_normalize_and_validate() -> None:
    """The shared module must expose both ``normalize_phone`` and ``validate_phone``."""
    canonical = importlib.import_module("src.phone_utils")
    assert hasattr(canonical, "normalize_phone")
    assert hasattr(canonical, "validate_phone")
    # Back-compat shim must re-export the same callables.
    shim = importlib.import_module("telegram_bot.phone_utils")
    assert shim.normalize_phone is canonical.normalize_phone
    assert shim.validate_phone is canonical.validate_phone


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


# test_mini_app_phone_no_local_regex_validator — REMOVED (Mini App archived)
# test_mini_app_phone_imports_shared_normalizer — REMOVED (Mini App archived)


def test_phone_keyboard_re_exports_or_uses_shared_module() -> None:
    """``phone_keyboard.py`` must consume the shared module so there is one
    source of truth for the validation/normalization logic.

    Accepts either ``telegram_bot.phone_utils`` (shim) or the canonical
    ``src.phone_utils`` import — both point to the same implementation.
    """
    tree = ast.parse(PHONE_KEYBOARD_PATH.read_text(encoding="utf-8"))
    used_shared = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in (
            "telegram_bot.phone_utils",
            "src.phone_utils",
        ):
            used_shared = True
            break
    assert used_shared, (
        "telegram_bot/keyboards/phone_keyboard.py must import phone "
        "normalization from telegram_bot.phone_utils or src.phone_utils to "
        "keep one source of truth."
    )


# ---------------------------------------------------------------------------
# Mini App tests removed — Mini App is permanently archived.
# (test_mini_app_phone_no_local_regex_validator,
#  test_mini_app_phone_imports_shared_normalizer,
#  test_pydantic_phone_request_normalizes_to_e164,
#  test_pydantic_phone_request_rejects_impossible_numbers)
# ---------------------------------------------------------------------------
