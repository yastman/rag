#!/usr/bin/env python3
"""Bot response smoke gate (#2192).

End-to-end gate proving "local bot starts and answers". Runs five
preflight checks, then sends a single safe Telegram message via the
existing Telethon e2e infrastructure (``scripts.e2e.quick_test``).

Preflight stages (run sequentially, fail fast):

1. ``ENV``     — TELEGRAM_API_ID, TELEGRAM_API_HASH, E2E_BOT_USERNAME,
                 TELEGRAM_BOT_TOKEN are present.
2. ``SESSION`` — ``e2e_tester.session`` exists on disk; the probe never
                 attempts to (re-)authorize the userbot itself.
3. ``GETME``   — Telegram Bot API ``getMe`` username matches
                 ``E2E_BOT_USERNAME`` (#2192 acceptance).
4. ``WEBHOOK`` — ``getWebhookInfo`` reports an empty URL so polling mode
                 is in use.
5. ``LOCK``    — Redis ``telegram-bot:polling`` key is read but not
                 deleted; the probe surfaces owner+TTL so the operator
                 can decide whether ``make bot`` is the holder or a
                 stale duplicate.

If all pre-flight stages succeed, the probe delegates to
``scripts.e2e.quick_test.main`` to send one query and assert a
non-empty response. Failures at any stage exit with the matching
:class:`PreflightStage` code and an actionable remediation.

CLI::

    uv run python -m scripts.probe.bot_response_smoke

Refs #2192.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

DEFAULT_SESSION_PATH = Path("e2e_tester.session")
TELEGRAM_API_BASE = "https://api.telegram.org"
POLLING_LOCK_KEY = "telegram-bot:polling"


class PreflightStage(StrEnum):
    ENV = "env"
    SESSION = "session"
    GETME = "getme"
    WEBHOOK = "webhook"
    LOCK = "lock"


@dataclass(slots=True)
class PreflightResult:
    """Outcome of one preflight stage."""

    stage: PreflightStage
    ok: bool
    detail: str = ""
    remediation: str = ""


class PreflightError(SystemExit):
    """Raised when a preflight stage fails. Carries stage + remediation."""

    def __init__(self, *, stage: PreflightStage, detail: str, remediation: str = "") -> None:
        self.stage = stage
        self.detail = detail
        self.remediation = remediation
        msg = f"[{stage.value}] {detail}"
        if remediation:
            msg = f"{msg}\n  remediation: {remediation}"
        super().__init__(msg)


# ---------------------------------------------------------------------------
# 1. Env vars
# ---------------------------------------------------------------------------

REQUIRED_ENV_VARS: tuple[str, ...] = (
    "TELEGRAM_API_ID",
    "TELEGRAM_API_HASH",
    "E2E_BOT_USERNAME",
    "TELEGRAM_BOT_TOKEN",
)


def check_env_vars() -> PreflightResult:
    """Verify required env vars are present (without echoing their values)."""
    missing = [var for var in REQUIRED_ENV_VARS if not os.environ.get(var)]
    if missing:
        return PreflightResult(
            stage=PreflightStage.ENV,
            ok=False,
            detail=f"missing env vars: {', '.join(missing)}",
            remediation=(
                "fill TELEGRAM_API_ID and TELEGRAM_API_HASH in .env from "
                "https://my.telegram.org; set E2E_BOT_USERNAME and "
                "TELEGRAM_BOT_TOKEN to the local bot identity"
            ),
        )
    return PreflightResult(stage=PreflightStage.ENV, ok=True)


# ---------------------------------------------------------------------------
# 2. Session file present
# ---------------------------------------------------------------------------


def check_session_authorized(session_path: Path = DEFAULT_SESSION_PATH) -> PreflightResult:
    """Verify the Telethon session file exists.

    The probe deliberately does not try to authorize the userbot — that
    requires interactive input and lives in :mod:`scripts.e2e.auth`.
    """
    if not session_path.exists():
        return PreflightResult(
            stage=PreflightStage.SESSION,
            ok=False,
            detail=f"Telethon session file not found: {session_path}",
            remediation="run: uv run python -m scripts.e2e.auth to authorize the userbot",
        )
    return PreflightResult(stage=PreflightStage.SESSION, ok=True)


# ---------------------------------------------------------------------------
# 3. Bot username matches token
# ---------------------------------------------------------------------------


async def check_username_matches_token(
    *, token: str, expected_username: str, client: Any
) -> PreflightResult:
    """Compare ``getMe`` username against ``E2E_BOT_USERNAME``."""
    expected = expected_username.lstrip("@")
    url = f"{TELEGRAM_API_BASE}/bot{token}/getMe"
    try:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # network / auth errors → actionable message
        return PreflightResult(
            stage=PreflightStage.GETME,
            ok=False,
            detail=f"getMe call failed: {type(exc).__name__}",
            remediation="verify TELEGRAM_BOT_TOKEN is valid and Telegram API is reachable",
        )

    actual = (payload.get("result") or {}).get("username", "")
    if actual.lstrip("@").lower() != expected.lower():
        return PreflightResult(
            stage=PreflightStage.GETME,
            ok=False,
            detail=f"E2E_BOT_USERNAME=@{expected} but TELEGRAM_BOT_TOKEN belongs to @{actual}",
            remediation=(
                "set E2E_BOT_USERNAME to match the token, or rotate the token "
                "to one belonging to the expected bot identity"
            ),
        )
    return PreflightResult(stage=PreflightStage.GETME, ok=True)


# ---------------------------------------------------------------------------
# 4. Webhook disabled (polling mode)
# ---------------------------------------------------------------------------


async def check_webhook_disabled(*, token: str, client: Any) -> PreflightResult:
    """Polling mode requires ``getWebhookInfo`` URL to be empty."""
    url = f"{TELEGRAM_API_BASE}/bot{token}/getWebhookInfo"
    try:
        response = await client.get(url, timeout=10.0)
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return PreflightResult(
            stage=PreflightStage.WEBHOOK,
            ok=False,
            detail=f"getWebhookInfo call failed: {type(exc).__name__}",
            remediation="verify TELEGRAM_BOT_TOKEN and Telegram API connectivity",
        )

    info = payload.get("result") or {}
    webhook_url = info.get("url", "")
    if webhook_url:
        return PreflightResult(
            stage=PreflightStage.WEBHOOK,
            ok=False,
            detail=(
                f"webhook URL is set ({webhook_url}); polling-mode bot will not "
                f"receive updates while a webhook is registered"
            ),
            remediation="curl -fsS -X POST $TELEGRAM_API_BASE/bot$TELEGRAM_BOT_TOKEN/deleteWebhook",
        )
    return PreflightResult(stage=PreflightStage.WEBHOOK, ok=True)


# ---------------------------------------------------------------------------
# 5. Polling lock surface (informational, never deletes)
# ---------------------------------------------------------------------------


async def check_polling_lock_free(*, redis: Any, key: str = POLLING_LOCK_KEY) -> PreflightResult:
    """Surface polling-lock owner and TTL without deleting the key.

    The probe never deletes ``telegram-bot:polling`` (#2189). A held lock
    is reported with owner+TTL so the operator can decide whether
    ``make bot`` is the legitimate holder or a duplicate must be stopped.
    """
    owner = await redis.get(key)
    if owner is None:
        return PreflightResult(stage=PreflightStage.LOCK, ok=True)
    if isinstance(owner, bytes):
        owner = owner.decode("utf-8", errors="replace")
    pttl = await redis.pttl(key)
    return PreflightResult(
        stage=PreflightStage.LOCK,
        ok=True,  # informational: not a hard fail
        detail=f"polling lock held — owner={owner} pttl_ms={pttl}",
        remediation=(
            "if make bot is the owner, this is expected; otherwise stop the "
            "other instance before sending the smoke message"
        ),
    )


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


async def run_preflight() -> list[PreflightResult]:
    """Run all preflight stages and return per-stage results."""
    results: list[PreflightResult] = []
    results.append(check_env_vars())
    results.append(check_session_authorized())

    if results[0].ok:
        token = os.environ["TELEGRAM_BOT_TOKEN"]
        username = os.environ["E2E_BOT_USERNAME"]
        try:
            import httpx
        except ImportError:
            logger.warning("httpx not available — skipping getMe / getWebhookInfo checks")
            return results

        async with httpx.AsyncClient() as client:
            results.append(
                await check_username_matches_token(
                    token=token,
                    expected_username=username,
                    client=client,
                )
            )
            results.append(await check_webhook_disabled(token=token, client=client))

        # Lock check best-effort — Redis may not be reachable, but we already
        # have other channels (preflight-bot) that signal that.
        try:
            import redis.asyncio as aioredis  # type: ignore[import-not-found]

            redis_url = os.environ.get(
                "REDIS_URL",
                f"redis://:{os.environ.get('REDIS_PASSWORD', '')}@localhost:6379/0",
            )
            r = aioredis.from_url(redis_url, decode_responses=True)
            try:
                results.append(await check_polling_lock_free(redis=r))
            finally:
                await r.aclose()
        except Exception as exc:
            logger.warning("polling lock probe skipped: %s", exc)

    return results


def _print_results(results: list[PreflightResult]) -> bool:
    """Print results table; return True iff all required stages passed."""
    all_ok = True
    for r in results:
        marker = "✓" if r.ok else "✗"
        line = f"  [{r.stage.value}] {marker}"
        if r.detail:
            line += f" {r.detail}"
        print(line)
        if r.remediation and (not r.ok or r.detail):
            print(f"      remediation: {r.remediation}")
        if not r.ok:
            all_ok = False
    return all_ok


async def _async_main(skip_send: bool) -> int:
    print("Bot response smoke preflight")
    results = await run_preflight()
    all_ok = _print_results(results)
    if not all_ok:
        print("\nPreflight failed — refusing to send smoke message.")
        return 1
    if skip_send:
        print("\nPreflight passed — skipping send (--skip-send).")
        return 0

    print("\nPreflight passed — delegating to scripts.e2e.quick_test ...")
    from scripts.e2e import quick_test

    return await quick_test.main()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bot response smoke gate: preflight + Telethon send (#2192).",
    )
    parser.add_argument(
        "--skip-send",
        action="store_true",
        help="Run preflight only; do not send a Telegram message.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    return asyncio.run(_async_main(skip_send=args.skip_send))


if __name__ == "__main__":
    sys.exit(main())
