"""Re-export shim for ``src.phone_utils`` (#1948 layering fix).

The canonical home of the shared phone-normalization helpers is now
``src/phone_utils.py`` so ``mini_app/`` and ``src/api/`` can import them
without taking a dependency on ``telegram_bot.*`` (see #1948 layering
contract).

This shim keeps existing bot internal callers
(``telegram_bot/keyboards/phone_keyboard.py``) working unchanged; new code
should import from ``src.phone_utils`` directly. The shim has no behavior
of its own and cannot drift from the canonical implementation.
"""

from __future__ import annotations

from src.phone_utils import normalize_phone, validate_phone


__all__ = ["normalize_phone", "validate_phone"]
