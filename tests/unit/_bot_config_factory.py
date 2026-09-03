"""Shared BotConfig factory helpers for unit tests.

Centralises the duplicated _make_config() pattern that appeared in
~10 unit test files (#2989).

Two variants:
- ``make_bot_config(**overrides)``  – minimal fields, accepts keyword overrides.
- ``make_full_bot_config(**overrides)`` – full fields (qdrant_api_key,
  qdrant_collection, realestate_database_url), accepts keyword overrides.
"""

from __future__ import annotations

from telegram_bot.config import BotConfig


_MINIMAL_DEFAULTS: dict[str, object] = {
    "telegram_token": "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi",
    "llm_api_key": "llm-key",
    "llm_base_url": "https://api.example.com/v1",
    "llm_model": "gpt-4o-mini",
    "qdrant_url": "http://localhost:6333",
    "redis_url": "redis://localhost:6379",
    "rerank_provider": "none",
}

_FULL_DEFAULTS: dict[str, object] = {
    **_MINIMAL_DEFAULTS,
    "qdrant_api_key": "qdrant-key",
    "qdrant_collection": "test_collection",
    "realestate_database_url": "postgresql://postgres:postgres@127.0.0.1:1/realestate",
}


def make_bot_config(**overrides: object) -> BotConfig:
    """Return a minimal BotConfig with test defaults, accepting overrides."""
    return BotConfig(_env_file=None, **{**_MINIMAL_DEFAULTS, **overrides})


def make_full_bot_config(**overrides: object) -> BotConfig:
    """Return a full BotConfig (qdrant_api_key, db) with test defaults."""
    return BotConfig(_env_file=None, **{**_FULL_DEFAULTS, **overrides})
