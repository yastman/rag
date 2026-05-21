***REMOVED*** tests/contract/test_shared_phone_normalization_contract.py
"""Contract: Mini App phone capture must reuse the shared phonenumbers-based
normalization, not redeclare a digit-count regex.

Closes ***REMOVED***1614.

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
MINI_APP_PHONE_PATH = REPO_ROOT / "mini_app" / "phone.py"
PHONE_KEYBOARD_PATH = REPO_ROOT / "telegram_bot" / "keyboards" / "phone_keyboard.py"
PHONE_UTILS_PATH = REPO_ROOT / "telegram_bot" / "phone_utils.py"


def test_shared_phone_utils_module_exists() -> None:
    """A non-UI helper module must exist as the single source of truth."""
    assert PHONE_UTILS_PATH.exists(), (
        f"missing {PHONE_UTILS_PATH} — phone normalization must live in a "
        "non-UI module so Mini App and bot can share it without dragging in "
        "aiogram keyboard imports."
    )


def test_shared_phone_utils_exports_normalize_and_validate() -> None:
    """The shared module must expose both ``normalize_phone`` and ``validate_phone``."""
    module = importlib.import_module("telegram_bot.phone_utils")
    assert hasattr(module, "normalize_phone")
    assert hasattr(module, "validate_phone")


def test_shared_phone_utils_does_not_import_aiogram() -> None:
    """The shared module must be UI-free so Mini App can import it without
    pulling aiogram keyboard types."""
    src = PHONE_UTILS_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("aiogram"), (
                    f"telegram_bot/phone_utils.py imports {alias.name}; "
                    "shared phone normalization must stay UI-free."
                )
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith("aiogram"), (
                f"telegram_bot/phone_utils.py imports from {mod}; "
                "shared phone normalization must stay UI-free."
            )


def test_mini_app_phone_no_local_regex_validator() -> None:
    """``mini_app/phone.py`` must not redeclare its own digit-count regex."""
    src = MINI_APP_PHONE_PATH.read_text(encoding="utf-8")
    assert "_PHONE_RE" not in src, (
        "mini_app/phone.py still defines _PHONE_RE; consume the shared "
        "telegram_bot.phone_utils.normalize_phone helper instead."
    )
    assert "\\d{7,15}" not in src, (
        "mini_app/phone.py still uses the digit-count regex; that pattern "
        "accepts impossible numbers like +11111111111 and never normalizes "
        "to E.164. Reuse the phonenumbers-based normalize_phone helper."
    )


def test_mini_app_phone_imports_shared_normalizer() -> None:
    """``mini_app/phone.py`` must import the shared ``normalize_phone``."""
    tree = ast.parse(MINI_APP_PHONE_PATH.read_text(encoding="utf-8"))
    imported_normalize = False
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "telegram_bot.phone_utils"
            and any(alias.name == "normalize_phone" for alias in node.names)
        ):
            imported_normalize = True
            break
    assert imported_normalize, (
        "mini_app/phone.py must import normalize_phone from "
        "telegram_bot.phone_utils."
    )


def test_phone_keyboard_re_exports_or_uses_shared_module() -> None:
    """``phone_keyboard.py`` must consume the shared module so there is one
    source of truth for the validation/normalization logic."""
    tree = ast.parse(PHONE_KEYBOARD_PATH.read_text(encoding="utf-8"))
    used_shared = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "telegram_bot.phone_utils":
            used_shared = True
            break
    assert used_shared, (
        "telegram_bot/keyboards/phone_keyboard.py must import phone "
        "normalization from telegram_bot.phone_utils to keep one source of "
        "truth."
    )


def test_pydantic_phone_request_normalizes_to_e164() -> None:
    """Behavioral guard: ``PhoneRequest`` must store the E.164-normalized
    value, not the raw input."""
    from mini_app.phone import PhoneRequest

    request = PhoneRequest(
        phone="+359 888 123 456",
        source="test",
        user_id=42,
    )
    assert request.phone == "+359888123456", (
        f"PhoneRequest must normalize phone to E.164 form; got {request.phone!r}"
    )


def test_pydantic_phone_request_rejects_impossible_numbers() -> None:
    """Behavioral guard: numbers that match the old digit-count regex but are
    not real phone numbers must be rejected (they used to slip through)."""
    import pytest
    from pydantic import ValidationError

    from mini_app.phone import PhoneRequest

    ***REMOVED*** All-1s: 11 digits, regex-valid, phonenumbers-invalid.
    with pytest.raises(ValidationError):
        PhoneRequest(phone="+11111111111", source="test", user_id=42)

    ***REMOVED*** Letters: matches neither regex nor phonenumbers.
    with pytest.raises(ValidationError):
        PhoneRequest(phone="not-a-phone", source="test", user_id=42)
