#!/usr/bin/env python3
"""Preflight guard for ``make bot`` / ``make docker-bot-up`` runtime environment.

Detects and explains:

* missing ``.env`` file (CI fallback is used instead)
* invalid/placeholder ``TELEGRAM_BOT_TOKEN`` that will crash the bot
* ``LiteLLM`` ``localhost:4000`` not published (common stray-compose-file issue)

Usage::

    # Default: check the effective env file for local development
    python scripts/probe/check_bot_runtime_env.py

    # Explicit env file
    python scripts/probe/check_bot_runtime_env.py --env-file .env

    # Warn-only (exit 0 even when issues found — use in CI)
    python scripts/probe/check_bot_runtime_env.py --no-fail

Exit codes
    0  all clear, or ``--no-fail`` was given
    1  critical issues found — expect ``make bot`` / ``make docker-bot-up`` to fail
    2  Docker not available (LiteLLM port check skipped, non-fatal)

Related issues: `#2123 <https://github.com/yastman/rag/issues/2123>`_,
`#2126 <https://github.com/yastman/rag/issues/2126>`_.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import NoReturn


# ---------------------------------------------------------------------------
# Well-known CI fallback values that are NEVER valid for real bot operation
# ---------------------------------------------------------------------------

_CI_TELEGRAM_BOT_TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi"  # nosec B105

# Regex-based format check:  <bot_id>:<bot_token>
# aiogram.aiogram.utils.token.TokenValidationError is the authoritative check,
# but we also want to catch the exact CI placeholder value before any SDK call.
_TOKEN_PATTERN = r"^\d+:[A-Za-z\d_-]{35,}$"  # nosec B105

# ---------------------------------------------------------------------------
# Env file resolution (mirrors Makefile LOCAL_COMPOSE_CMD / RUNTIME_ENV_FILE)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CI_ENV_FILE = _REPO_ROOT / "tests" / "fixtures" / "compose.ci.env"
_ENV_EXAMPLE = _REPO_ROOT / ".env.example"
_DOTENV = _REPO_ROOT / ".env"


def _resolve_env_file(explicit: str | None) -> tuple[Path, bool]:
    """Resolve the effective env file and whether .env was found.

    Returns ``(env_file_path, dotenv_found)``.
    """
    if explicit:
        p = Path(explicit)
        return p.resolve(), p.name == ".env" and p.exists()
    if _DOTENV.is_file():
        return _DOTENV, True
    return _CI_ENV_FILE, False


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _check_env_presence(dotenv_found: bool) -> list[str]:
    """Report whether .env is present or the CI fallback is active."""
    issues: list[str] = []

    if dotenv_found:
        issues.append("  .env: found  ✓")
    else:
        issues.append("  .env: MISSING  ✗")
        issues.append("    CI fallback env is active: tests/fixtures/compose.ci.env")
        issues.append(
            "    The CI fallback contains placeholder credentials that are "
            "NOT valid for real bot operation."
        )
        issues.append("    Remediation:   cp .env.example .env   then fill real credentials.")
    return issues


def _check_telegram_token(env_file: Path) -> list[str]:
    """Validate TELEGRAM_BOT_TOKEN from the effective env file."""
    import re

    issues: list[str] = []
    token_value = _read_env_var(env_file, "TELEGRAM_BOT_TOKEN")

    if token_value is None:
        issues.append("  TELEGRAM_BOT_TOKEN: MISSING  ✗")
        issues.append("    The bot will fail to start without a Telegram bot token.")
        issues.append("    Remediation: set TELEGRAM_BOT_TOKEN in .env from @BotFather.")
        return issues

    # Exact match to the well-known CI fallback
    if token_value == _CI_TELEGRAM_BOT_TOKEN:
        issues.append("  TELEGRAM_BOT_TOKEN: CI placeholder  ✗")
        issues.append(
            "    Value is the CI-only fallback '123456789:ABC...fghi'. "
            "This is NOT a real Telegram token."
        )
        issues.append("    Effect: the bot will crash-loop with TokenValidationError (see #2126).")
        issues.append("    Remediation: set a real TELEGRAM_BOT_TOKEN in .env from @BotFather.")
        return issues

    if not re.match(_TOKEN_PATTERN, token_value):
        issues.append("  TELEGRAM_BOT_TOKEN: possibly invalid format  ✗")
        issues.append("    The token does not match the expected '<bot_id>:<token>' format.")
        issues.append("    Effect: the bot will fail with TokenValidationError at startup.")
        issues.append("    Remediation: verify your TELEGRAM_BOT_TOKEN in .env.")
        return issues

    issues.append("  TELEGRAM_BOT_TOKEN: present (real value)  ✓")
    return issues


def _check_polling_lock_probe(env_file: Path) -> list[str]:
    """Check if a Redis polling lock is held by another bot instance (issue #2189)."""
    issues: list[str] = []
    redis_url = _read_env_var(env_file, "REDIS_URL")
    if not redis_url:
        redis_password = _read_env_var(env_file, "REDIS_PASSWORD") or ""
        redis_host = _read_env_var(env_file, "REDIS_HOST") or "localhost"
        redis_port = _read_env_var(env_file, "REDIS_PORT") or "6379"
        if redis_password:
            redis_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"
        else:
            redis_url = f"redis://{redis_host}:{redis_port}/0"

    try:
        import redis

        r = redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=3)
        owner = r.get("telegram-bot:polling")
        if owner is None:
            issues.append("  Polling lock: free  ✓")
        else:
            pttl = r.pttl("telegram-bot:polling")
            issues.append("  Polling lock: BUSY  ✗")
            issues.append("    key: telegram-bot:polling")
            issues.append(f"    owner: {owner}")
            issues.append(f"    pttl_ms: {pttl}")
            issues.append(
                "    Remediation: stop the other bot process if alive, "
                "or wait for TTL expiry. Do NOT delete the key manually "
                "unless you are certain the owner process is dead."
            )
        r.close()
    except ImportError:
        issues.append("  Polling lock: skipped (redis package not available)")
    except Exception as exc:
        issues.append(f"  Polling lock: skipped (Redis unreachable: {exc})")

    return issues


def _check_litellm_port() -> list[str]:
    """Check whether LiteLLM port 4000 is published on the Docker host.

    This only runs when Docker is available.  A missing port binding is
    most commonly caused by a stray third compose file
    (e.g. ``/tmp/compose.postgres-root.yml``) that sets ``ports: []``,
    overriding the ``compose.dev.yml`` ``"127.0.0.1:4000:4000"`` mapping.
    """
    issues: list[str] = []

    if not shutil.which("docker"):
        issues.append("  LiteLLM port: Docker not available (skipped)")
        return issues

    try:
        # fixed docker subcommand with no shell expansion.
        cp = subprocess.run(  # nosec B603 B607
            [
                "docker",
                "inspect",
                "dev-litellm-1",
                "--format",
                "{{json .HostConfig.PortBindings}}",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        issues.append("  LiteLLM port: Docker unreachable (skipped)")
        return issues

    if cp.returncode != 0:
        issues.append("  LiteLLM port: container dev-litellm-1 not found (skipped)")
        return issues

    import json

    try:
        bindings = json.loads(cp.stdout.strip())
    except json.JSONDecodeError:
        issues.append("  LiteLLM port: could not parse Docker output (skipped)")
        return issues

    # When PortBindings is empty/null, no host ports are published.
    if not bindings:
        issues.append("  LiteLLM port 4000: NOT published on host  ✗")
        issues.append("    dev-litellm-1 container is running but no host port mapping exists.")
        issues.append(
            "    Effect: LLM-dependent features (make bot, test-bot-health) "
            "will fail with Connection Refused."
        )
        issues.append(
            "    Common cause: a stray compose file (e.g. "
            "/tmp/compose.postgres-root.yml) overrides the litellm port "
            "binding from compose.dev.yml ('127.0.0.1:4000:4000')."
        )
        issues.append(
            "    Remediation: remove any stray compose files overriding litellm "
            "ports, then run: make docker-bot-up"
        )
    else:
        issues.append("  LiteLLM port 4000: published  ✓")

    return issues


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_env_var(env_file: Path, key: str) -> str | None:
    """Read a single KEY=VALUE from a simple dotenv file (no shell syntax)."""
    try:
        text = env_file.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        if k.strip() == key:
            return v.strip()
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Preflight guard for make bot / make docker-bot-up.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=("Related: #2123 (restore Docker stack), #2126 (bot profile runtime).\n"),
    )
    p.add_argument(
        "--env-file",
        default=None,
        help="Path to the effective env file (default: .env if present, else CI fixture)",
    )
    p.add_argument(
        "--no-fail",
        action="store_true",
        help="Print issues but always exit 0 (e.g. in CI).",
    )
    p.add_argument(
        "--skip-docker",
        action="store_true",
        help="Skip Docker/LiteLLM port checks.",
    )
    return p


def main(argv: list[str] | None = None) -> NoReturn:
    parser = _build_parser()
    args = parser.parse_args(argv)
    all_issues: list[str] = []
    exit_code = 0

    # Resolve effective env file
    env_file, dotenv_found = _resolve_env_file(args.env_file)
    all_issues.append("Bot runtime environment preflight")
    all_issues.append(f"  Effective env file: {env_file}")
    all_issues.append("")

    # .env presence
    all_issues.extend(_check_env_presence(dotenv_found))

    # Empty separator
    all_issues.append("")

    # TELEGRAM_BOT_TOKEN
    all_issues.extend(_check_telegram_token(env_file))

    all_issues.append("")

    # Polling lock (issue #2189)
    if args.skip_docker:
        all_issues.append("  Polling lock: skipped (--skip-docker)")
    else:
        all_issues.extend(_check_polling_lock_probe(env_file))

    all_issues.append("")

    # LiteLLM port (skip if requested or Docker not available)
    if args.skip_docker:
        all_issues.append("  LiteLLM port: skipped (--skip-docker)")
    else:
        all_issues.extend(_check_litellm_port())

    all_issues.append("")

    # Determine overall status
    severity = _classify(all_issues)

    if severity == "ok":
        all_issues.append("All bot runtime preflight checks passed.")
        exit_code = 0
    else:
        all_issues.append("One or more issues found. The bot may fail to start or operate.")
        all_issues.append(
            "Affected targets:   make bot   make docker-bot-up   make test-bot-health"
        )
        all_issues.append(
            "For safe local development:   cp .env.example .env   "
            "then fill TELEGRAM_BOT_TOKEN and a provider key."
        )
        exit_code = 1 if not args.no_fail else 0

    out = "\n".join(all_issues) + "\n"
    sys.stdout.write(out)
    sys.exit(exit_code)


def _classify(lines: list[str]) -> str:
    """Return 'ok' if no ✗ markers, otherwise 'issues'."""
    for line in lines:
        if "✗" in line:
            return "issues"
    return "ok"


if __name__ == "__main__":
    main()
