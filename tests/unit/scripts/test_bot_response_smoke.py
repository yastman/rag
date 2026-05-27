"""Tests for scripts/probe/bot_response_smoke.py preflight (#2192).

The probe must validate env, session, getMe match, webhook, and polling
lock BEFORE attempting to send a Telegram message. Each pre-flight stage
exits with a precise, actionable error on failure and never sends a
message when any guard fails.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.probe.bot_response_smoke import (
    POLLING_LOCK_KEY,
    PreflightError,
    PreflightStage,
    check_env_vars,
    check_polling_lock_free,
    check_session_authorized,
    check_username_matches_token,
    check_webhook_disabled,
)


# ---------------------------------------------------------------------------
# 1. Env vars
# ---------------------------------------------------------------------------


def test_check_env_vars_passes_when_all_present(monkeypatch) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc123")
    monkeypatch.setenv("E2E_BOT_USERNAME", "@my_bot")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "11:abc")
    result = check_env_vars()
    assert result.ok is True
    assert result.stage == PreflightStage.ENV


def test_check_env_vars_fails_when_api_id_missing(monkeypatch) -> None:
    monkeypatch.delenv("TELEGRAM_API_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_API_HASH", "abc")
    monkeypatch.setenv("E2E_BOT_USERNAME", "@b")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "11:abc")
    result = check_env_vars()
    assert result.ok is False
    assert "TELEGRAM_API_ID" in result.detail
    # Remediation must point operators back to local env setup.
    assert ".env" in result.remediation


def test_check_env_vars_does_not_print_secret_values(
    monkeypatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TELEGRAM_API_ID", "12345")
    monkeypatch.setenv("TELEGRAM_API_HASH", "REALsecretHASH9876")
    monkeypatch.setenv("E2E_BOT_USERNAME", "@b")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "11:REALsecretTOKEN")
    check_env_vars()
    out = capsys.readouterr().out
    assert "REALsecretHASH9876" not in out, "must not echo TELEGRAM_API_HASH"
    assert "REALsecretTOKEN" not in out, "must not echo TELEGRAM_BOT_TOKEN"


# ---------------------------------------------------------------------------
# 2. Session authorized
# ---------------------------------------------------------------------------


def test_check_session_authorized_fails_when_session_file_missing(tmp_path: Path) -> None:
    result = check_session_authorized(session_path=tmp_path / "no_such")
    assert result.ok is False
    assert "session" in result.detail.lower()
    # Remediation must point operators at the auth command.
    assert "scripts.e2e.auth" in result.remediation or "authorize" in result.remediation.lower()


def test_check_session_authorized_passes_when_session_file_exists(tmp_path: Path) -> None:
    session = tmp_path / "e2e_tester.session"
    session.write_bytes(b"sqlite3 fake")
    result = check_session_authorized(session_path=session)
    assert result.ok is True


# ---------------------------------------------------------------------------
# 3. Bot username matches token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_username_matches_token_passes_when_getme_returns_same_username() -> None:
    fake_response = {"ok": True, "result": {"username": "my_bot"}}
    httpx_client = MagicMock()
    response = MagicMock()
    response.json = MagicMock(return_value=fake_response)
    response.raise_for_status = MagicMock()
    httpx_client.get = AsyncMock(return_value=response)

    result = await check_username_matches_token(
        token="11:abc",
        expected_username="@my_bot",
        client=httpx_client,
    )
    assert result.ok is True


@pytest.mark.asyncio
async def test_username_matches_token_fails_when_getme_returns_different_username() -> None:
    fake_response = {"ok": True, "result": {"username": "other_bot"}}
    httpx_client = MagicMock()
    response = MagicMock()
    response.json = MagicMock(return_value=fake_response)
    response.raise_for_status = MagicMock()
    httpx_client.get = AsyncMock(return_value=response)

    result = await check_username_matches_token(
        token="11:abc",
        expected_username="@my_bot",
        client=httpx_client,
    )
    assert result.ok is False
    assert "my_bot" in result.detail and "other_bot" in result.detail


# ---------------------------------------------------------------------------
# 4. Webhook disabled
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_disabled_passes_when_url_empty() -> None:
    fake = {"ok": True, "result": {"url": "", "pending_update_count": 0}}
    httpx_client = MagicMock()
    response = MagicMock()
    response.json = MagicMock(return_value=fake)
    response.raise_for_status = MagicMock()
    httpx_client.get = AsyncMock(return_value=response)

    result = await check_webhook_disabled(token="11:abc", client=httpx_client)
    assert result.ok is True


@pytest.mark.asyncio
async def test_webhook_disabled_fails_when_url_set() -> None:
    fake = {"ok": True, "result": {"url": "https://x.example/webhook", "pending_update_count": 5}}
    httpx_client = MagicMock()
    response = MagicMock()
    response.json = MagicMock(return_value=fake)
    response.raise_for_status = MagicMock()
    httpx_client.get = AsyncMock(return_value=response)

    result = await check_webhook_disabled(token="11:abc", client=httpx_client)
    assert result.ok is False
    assert "webhook" in result.detail.lower()


# ---------------------------------------------------------------------------
# 5. Polling lock free / explained
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_polling_lock_check_passes_when_lock_free() -> None:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=None)
    result = await check_polling_lock_free(redis=redis)
    assert result.ok is True


def test_polling_lock_key_uses_shared_runtime_constant() -> None:
    """Probe and bot preflight must share the canonical polling-lock key."""
    from src.runtime.integrations.polling_lock import POLLING_LOCK_KEY as SHARED_KEY

    assert POLLING_LOCK_KEY == SHARED_KEY


@pytest.mark.asyncio
async def test_polling_lock_check_explains_when_lock_busy() -> None:
    redis = MagicMock()
    redis.get = AsyncMock(return_value=b"WIN-HOST:12345")
    redis.pttl = AsyncMock(return_value=72000)
    result = await check_polling_lock_free(redis=redis)
    # The acceptance criteria say "explains that make bot must already be
    # running or duplicate must be stopped" — not a hard fail on lock held.
    # Lock-busy is acceptable IF make bot is the holder, but the probe must
    # surface owner+TTL so the operator can decide.
    assert result.detail
    assert "WIN-HOST:12345" in result.detail
    assert "72000" in result.detail or "72" in result.detail


# ---------------------------------------------------------------------------
# Stage ordering / failure surface
# ---------------------------------------------------------------------------


def test_preflight_error_carries_stage_and_remediation() -> None:
    err = PreflightError(stage=PreflightStage.SESSION, detail="missing", remediation="run auth")
    assert err.stage is PreflightStage.SESSION
    assert "missing" in str(err)
    assert err.remediation == "run auth"
