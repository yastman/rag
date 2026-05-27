"""Shared polling-lock constants for bot and preflight tooling."""

from __future__ import annotations


# Canonical Redis key for the bot polling lock. Keep this in ``src.runtime`` so
# out-of-process scripts do not import ``telegram_bot`` runtime modules.
POLLING_LOCK_KEY = "telegram-bot:polling"
