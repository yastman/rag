#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_ROOT"

exec uv run python - <<'PY'
import asyncio
import logging

import httpx

from telegram_bot.config import BotConfig
from telegram_bot.preflight import _check_single_dep, check_dependencies


logging.basicConfig(level=logging.INFO, format="%(message)s")


async def main() -> None:
    config = BotConfig()
    await check_dependencies(config, log_summary=True)
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        litellm_ok = await _check_single_dep("litellm", config, client)
    if not litellm_ok:
        raise SystemExit("make test-bot-health requires LiteLLM to be healthy")


asyncio.run(main())
PY
