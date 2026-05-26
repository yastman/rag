"""Wiring tests: Sentry must be initialized at every entry point (#1417).

Acceptance for #1417 closes the gap that ``initialize_sentry`` was implemented
(child issues #2060, #2061, #2062) but never wired into the runtime entry
points. Without these calls the helper is a dead module and a configured
``SENTRY_DSN`` does nothing.

Verified via Context7 (/getsentry/sentry-python): the SDK requires
``sentry_sdk.init()`` to be called **before any other SDK call**, typically
at application startup. We assert call order against ``initialize_langfuse``
so Sentry catches even Langfuse-init failures.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _cleanup_main_module():
    """Drop ``telegram_bot.main`` so each test re-imports a fresh module."""
    tracked = (
        "telegram_bot.main",
        "telegram_bot.bot",
        "telegram_bot.config",
        "telegram_bot.logging_config",
    )
    originals = {name: sys.modules.get(name) for name in tracked}
    pkg = sys.modules.get("telegram_bot")
    had_main_attr = pkg is not None and hasattr(pkg, "main")
    original_main_attr = getattr(pkg, "main", None) if had_main_attr else None
    for name in tracked:
        sys.modules.pop(name, None)
    if pkg is not None and hasattr(pkg, "main"):
        delattr(pkg, "main")
    yield
    for name, module in originals.items():
        if module is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = module
    if pkg is not None:
        if had_main_attr:
            pkg.main = original_main_attr
        elif hasattr(pkg, "main"):
            delattr(pkg, "main")


def _patch_aiogram_imports():
    """Provide minimal stand-ins for aiogram exception types main.py imports."""
    fake = MagicMock()
    fake.exceptions.TelegramConflictError = type("TelegramConflictError", (Exception,), {})
    fake.exceptions.TelegramNetworkError = type("TelegramNetworkError", (Exception,), {})
    fake.exceptions.TelegramRetryAfter = type("TelegramRetryAfter", (Exception,), {})
    fake.exceptions.TelegramServerError = type("TelegramServerError", (Exception,), {})
    fake.exceptions.TelegramUnauthorizedError = type("TelegramUnauthorizedError", (Exception,), {})
    return fake


async def test_main_calls_initialize_sentry_before_initialize_langfuse():
    """Sentry must be booted FIRST so it captures Langfuse-init exceptions."""
    mock_property_bot_instance = AsyncMock()
    mock_property_bot = MagicMock(return_value=mock_property_bot_instance)
    mock_bot_config = MagicMock()
    mock_setup_logging = MagicMock()

    mock_bot_mod = MagicMock()
    mock_bot_mod.PropertyBot = mock_property_bot
    mock_config_mod = MagicMock()
    mock_config_mod.BotConfig = mock_bot_config
    mock_logging_mod = MagicMock()
    mock_logging_mod.setup_logging = mock_setup_logging

    call_order: list[str] = []

    def _record_sentry(*args, **kwargs):
        call_order.append("sentry")
        return True

    def _record_set_tags(*args, **kwargs):
        call_order.append("sentry_tags")
        return

    def _record_langfuse(*args, **kwargs):
        call_order.append("langfuse")
        return MagicMock()

    with patch.dict(
        sys.modules,
        {
            "telegram_bot.bot": mock_bot_mod,
            "telegram_bot.config": mock_config_mod,
            "telegram_bot.logging_config": mock_logging_mod,
        },
    ):
        from telegram_bot import main as main_mod

        with (
            patch.object(main_mod, "initialize_langfuse", side_effect=_record_langfuse),
            patch.object(main_mod, "initialize_sentry", side_effect=_record_sentry, create=True),
            patch.object(main_mod, "set_runtime_tags", side_effect=_record_set_tags, create=True),
        ):
            await main_mod.main()

    # Sentry must come first; tags after init; Langfuse last.
    assert call_order[:3] == ["sentry", "sentry_tags", "langfuse"], (
        f"Sentry must be initialized before Langfuse (#1417). Order={call_order}"
    )


async def test_main_does_not_fail_when_sentry_dsn_unset():
    """When SENTRY_DSN is unset, initialize_sentry returns False and main proceeds."""
    mock_property_bot_instance = AsyncMock()
    mock_property_bot = MagicMock(return_value=mock_property_bot_instance)
    mock_bot_config = MagicMock()

    mock_bot_mod = MagicMock()
    mock_bot_mod.PropertyBot = mock_property_bot
    mock_config_mod = MagicMock()
    mock_config_mod.BotConfig = mock_bot_config
    mock_logging_mod = MagicMock()
    mock_logging_mod.setup_logging = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "telegram_bot.bot": mock_bot_mod,
            "telegram_bot.config": mock_config_mod,
            "telegram_bot.logging_config": mock_logging_mod,
        },
    ):
        from telegram_bot import main as main_mod

        with (
            patch.object(main_mod, "initialize_langfuse", return_value=MagicMock()),
            patch.object(main_mod, "initialize_sentry", return_value=False, create=True),
            patch.object(main_mod, "set_runtime_tags", create=True),
        ):
            # Must not raise; Sentry returning False is the documented disabled path.
            await main_mod.main()

        mock_property_bot_instance.start.assert_awaited()


async def test_main_set_runtime_tags_called_with_telegram_bot_service():
    """set_runtime_tags must label the service so Sentry events tag service=telegram-bot."""
    mock_property_bot_instance = AsyncMock()
    mock_property_bot = MagicMock(return_value=mock_property_bot_instance)
    mock_bot_config = MagicMock()

    mock_bot_mod = MagicMock()
    mock_bot_mod.PropertyBot = mock_property_bot
    mock_config_mod = MagicMock()
    mock_config_mod.BotConfig = mock_bot_config
    mock_logging_mod = MagicMock()
    mock_logging_mod.setup_logging = MagicMock()

    captured_kwargs: dict = {}

    def _capture(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with patch.dict(
        sys.modules,
        {
            "telegram_bot.bot": mock_bot_mod,
            "telegram_bot.config": mock_config_mod,
            "telegram_bot.logging_config": mock_logging_mod,
        },
    ):
        from telegram_bot import main as main_mod

        with (
            patch.object(main_mod, "initialize_langfuse", return_value=MagicMock()),
            patch.object(main_mod, "initialize_sentry", return_value=True, create=True),
            patch.object(main_mod, "set_runtime_tags", side_effect=_capture, create=True),
        ):
            await main_mod.main()

    assert captured_kwargs.get("service") == "telegram-bot", (
        f"set_runtime_tags must label service='telegram-bot'. Got {captured_kwargs}"
    )


# ---------------------------------------------------------------------------
# Voice agent wiring
# ---------------------------------------------------------------------------


def test_voice_agent_has_setup_sentry_helper():
    """src.voice.agent must expose _setup_sentry() (#1417)."""
    pytest.importorskip("livekit")
    import src.voice.agent as mod

    assert hasattr(mod, "_setup_sentry"), (
        "src/voice/agent.py must expose _setup_sentry() so the LiveKit voice "
        "process initializes Sentry on startup (#1417)."
    )
    assert callable(mod._setup_sentry)


def test_voice_setup_sentry_initializes_sentry_with_service_tag():
    """_setup_sentry() boots Sentry and tags the voice-agent service."""
    pytest.importorskip("livekit")
    import src.voice.agent as mod

    captured_kwargs: dict = {}

    def _capture(*args, **kwargs):
        captured_kwargs.update(kwargs)

    with (
        patch.object(mod, "initialize_sentry", return_value=True) as init_mock,
        patch.object(mod, "set_runtime_tags", side_effect=_capture),
    ):
        mod._setup_sentry()

    init_mock.assert_called_once_with()
    assert captured_kwargs.get("service") == "voice-agent", (
        f"voice _setup_sentry must tag service='voice-agent'. Got {captured_kwargs}"
    )


def test_voice_setup_sentry_skips_runtime_tags_when_disabled():
    """When SENTRY_DSN is unset, do not push runtime tags into the SDK."""
    pytest.importorskip("livekit")
    import src.voice.agent as mod

    with (
        patch.object(mod, "initialize_sentry", return_value=False),
        patch.object(mod, "set_runtime_tags") as tags_mock,
    ):
        mod._setup_sentry()

    tags_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Mini App wiring
# ---------------------------------------------------------------------------


async def test_mini_app_lifespan_initializes_sentry_before_redis():
    """mini_app lifespan boots Sentry before opening Redis (#1417)."""
    pytest.importorskip("fastapi")
    from fastapi import FastAPI

    from mini_app import api as mini_api

    call_order: list[str] = []

    def _record_sentry(*args, **kwargs):
        call_order.append("sentry")
        return True

    def _record_set_tags(*args, **kwargs):
        call_order.append("sentry_tags")

    fake_aioredis = MagicMock()
    fake_redis_client = MagicMock()
    fake_redis_client.aclose = AsyncMock()

    def _fake_from_url(*args, **kwargs):
        call_order.append("redis_from_url")
        return fake_redis_client

    fake_aioredis.from_url = _fake_from_url

    fake_redis_module = MagicMock()
    fake_redis_module.asyncio = fake_aioredis

    app = FastAPI()
    with (
        patch.object(mini_api, "initialize_sentry", side_effect=_record_sentry, create=True),
        patch.object(mini_api, "set_runtime_tags", side_effect=_record_set_tags, create=True),
        patch.dict(sys.modules, {"redis": fake_redis_module, "redis.asyncio": fake_aioredis}),
    ):
        async with mini_api.lifespan(app):
            assert call_order[:2] == ["sentry", "sentry_tags"], (
                f"Sentry must boot before Redis in mini_app lifespan. Order={call_order}"
            )
            assert "redis_from_url" in call_order
