# 2026-05-08 Telethon Readiness Gate

## Scope

Issue: #1443
Blocking context: #1307
Surface: `scripts/e2e/*` Telethon local runtime loop

This audit validates whether local Telethon E2E entrypoints are ready for a bounded connect/send/receive check without exposing sensitive credentials.

## Redacted Prerequisite Check

- `.env` present: `true`
- `TELEGRAM_API_ID` present: `true`
- `TELEGRAM_API_HASH` present: `true`
- `E2E_BOT_USERNAME` present: `true`
- `e2e_tester.session` present: `true`

## Commands Executed

```bash
uv run ruff check scripts/e2e/auth.py scripts/e2e/telegram_client.py scripts/e2e/config.py scripts/e2e/runner.py
uv run python scripts/e2e/runner.py --scenario 1.1 --no-judge
uv run python - <<'PY'
import asyncio
from telethon import TelegramClient
from scripts.e2e.config import E2EConfig

async def main():
    c = E2EConfig()
    client = TelegramClient(c.telegram_session, c.telegram_api_id, c.telegram_api_hash)
    await client.connect()
    try:
        print(f"connected={True}")
        print(f"authorized={await client.is_user_authorized()}")
    finally:
        await client.disconnect()

asyncio.run(main())
PY
```

## Findings

1. Repo-owned redaction leaks were present before the run:
   - `scripts/e2e/auth.py` printed API ID, phone, and authenticated account identity.
   - `scripts/e2e/telegram_client.py` logged account username/phone on connect.
   - `scripts/e2e/runner.py` printed configured bot username.
2. Local session authorization check result: `connected=true`, `authorized=false`.
3. `runner.py --scenario 1.1 --no-judge` now fails fast with a clear non-interactive blocker message when the session is unauthorized.

## Repo Fixes Applied

- Sanitized `scripts/e2e/auth.py` output to avoid exposing API ID, phone, and account identity.
- Updated `scripts/e2e/telegram_client.py` to use `connect()` + authorization gate, and to avoid identity logging.
- Updated `scripts/e2e/runner.py` to avoid bot-username echo and to render a concise blocker error instead of traceback on runtime auth gate failure.
- Updated `docs/LOCAL-DEVELOPMENT.md` with explicit requirement that Telethon session must be authorized.

## Gate Result

`blocked-on-local-credentials`

Reason: local Telethon session file exists but is not authorized, so send/receive against the configured bot cannot proceed yet.

## Next Step

Re-authorize the local session via `scripts/e2e/auth.py`, then rerun:

```bash
uv run python scripts/e2e/runner.py --scenario 1.1 --no-judge
```

On successful connect/send/receive, resume #1307 runtime trace validation loop.
