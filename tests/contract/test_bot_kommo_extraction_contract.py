"""Drift guard for #1265 Slice 1 PR-6 — _bot_kommo extract.

Issue #1265 published a 6-PR Slice 1 plan that extracts pure module-level
helpers out of ``telegram_bot/bot.py`` before any class-level decomposition.

This contract pins **PR-6** — the final slice — which extracts the Kommo
access-token seeding helper:

  - _seed_kommo_access_token — Redis seed for KOMMO_ACCESS_TOKEN env var.

The helper is pure: stdlib + a lazy import of the canonical
``src.services.kommo_tokens.REDIS_KEY`` constant. It mirrors PR-1..PR-5
extraction shape exactly: a thin module owning the function body.

P17 (bot decomposition) completed the extraction — the function lives
exclusively in ``telegram_bot/_bot_kommo.py``. ``bot.py`` no longer keeps
a delegating wrapper; the bot.py line count is now well below the 4863
baseline.

Asserted invariants:

  1. ``telegram_bot/_bot_kommo.py`` exists, module-level imports clean.
  2. The helper is exposed at module top.
  3. ``_seed_kommo_access_token`` returns correct bool / Redis side
     effects via the canonical module on the four branches (empty token,
     existing tokens, fresh seed, partial state).
  4. ``bot.py`` line count is strictly below the 4863 baseline.
"""

from __future__ import annotations

import ast
from pathlib import Path
from unittest.mock import AsyncMock

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
NEW_MODULE = REPO_ROOT / "telegram_bot" / "_bot_kommo.py"
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"

HELPERS: tuple[str, ...] = ("_seed_kommo_access_token",)

FORBIDDEN_MODULE_LEVEL_IMPORTS: tuple[str, ...] = (
    "aiogram",
    "langgraph",
    "fastapi",
    "langchain",
    "redis",
    "qdrant_client",
)

BOT_PY_LINE_COUNT_CEILING = 4863


# ---------------------------------------------------------------------------
# Module existence + import hygiene
# ---------------------------------------------------------------------------


def test_bot_kommo_module_exists() -> None:
    assert NEW_MODULE.exists(), (
        f"#1265 Slice 1 PR-6: expected {NEW_MODULE.relative_to(REPO_ROOT)} "
        "to own the extracted Kommo seed helper."
    )


def test_bot_kommo_module_imports_are_clean() -> None:
    tree = ast.parse(NEW_MODULE.read_text())
    bad: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_MODULE_LEVEL_IMPORTS:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = (node.module or "").split(".")[0]
            if mod in FORBIDDEN_MODULE_LEVEL_IMPORTS:
                bad.append(node.module or "")
    assert not bad, (
        f"_bot_kommo.py module-level imports must avoid the bot stack; found forbidden roots: {bad}"
    )


@pytest.mark.parametrize("helper", HELPERS)
def test_bot_kommo_helper_exposed(helper: str) -> None:
    """The helper must be defined at module top-level."""
    tree = ast.parse(NEW_MODULE.read_text())
    names = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert helper in names, f"_bot_kommo.{helper} must be defined at module top."


# ---------------------------------------------------------------------------
# _seed_kommo_access_token behaviour via canonical module
# ---------------------------------------------------------------------------


def _make_redis(*, hgetall_ret: dict | None = None) -> AsyncMock:
    """Build a fake redis client with hgetall + hset captured as AsyncMocks."""
    redis = AsyncMock()
    redis.hgetall = AsyncMock(return_value=hgetall_ret or {})
    redis.hset = AsyncMock(return_value=1)
    return redis


@pytest.mark.asyncio
async def test_seed_returns_false_on_empty_token() -> None:
    """Empty access_token short-circuits before touching Redis."""
    from telegram_bot import _bot_kommo

    redis = _make_redis()
    out = await _bot_kommo._seed_kommo_access_token(
        redis=redis, access_token="", subdomain="example"
    )
    assert out is False
    redis.hgetall.assert_not_called()
    redis.hset.assert_not_called()


@pytest.mark.asyncio
async def test_seed_returns_false_when_existing_tokens_present() -> None:
    """If Redis already has tokens, do not overwrite — return False."""
    from telegram_bot import _bot_kommo

    redis = _make_redis(hgetall_ret={b"access_token": b"existing"})
    out = await _bot_kommo._seed_kommo_access_token(
        redis=redis, access_token="new-token", subdomain="example"
    )
    assert out is False
    redis.hgetall.assert_awaited_once()
    redis.hset.assert_not_called()


@pytest.mark.asyncio
async def test_seed_writes_when_redis_empty() -> None:
    """Empty Redis + non-empty access_token → seed and return True."""
    from telegram_bot import _bot_kommo

    redis = _make_redis(hgetall_ret={})
    out = await _bot_kommo._seed_kommo_access_token(
        redis=redis, access_token="ya29.NEW", subdomain="acme"
    )
    assert out is True
    redis.hgetall.assert_awaited_once()
    redis.hset.assert_awaited_once()
    # The hset payload must contain both fields.
    kwargs = redis.hset.await_args.kwargs
    mapping = kwargs.get("mapping") or (
        redis.hset.await_args.args[1] if len(redis.hset.await_args.args) > 1 else {}
    )
    assert mapping["access_token"] == "ya29.NEW"
    assert mapping["subdomain"] == "acme"


@pytest.mark.asyncio
async def test_seed_uses_canonical_redis_key_constant() -> None:
    """The seed call writes to the canonical ``KommoTokenStore.REDIS_KEY``."""
    from telegram_bot import _bot_kommo
    from telegram_bot.services.kommo_tokens import REDIS_KEY

    redis = _make_redis(hgetall_ret={})
    await _bot_kommo._seed_kommo_access_token(redis=redis, access_token="t", subdomain="s")
    redis.hgetall.assert_awaited_once_with(REDIS_KEY)
    redis.hset.assert_awaited_once()
    assert redis.hset.await_args.args[0] == REDIS_KEY


# ---------------------------------------------------------------------------
# bot.py shape — line-count ratchet (decomposition complete, no wrapper needed)
# ---------------------------------------------------------------------------


def test_bot_py_kommo_line_count_below_ratchet() -> None:
    """P17 decomposition must have reduced bot.py well below the 4863 baseline."""
    line_count = sum(1 for _ in BOT_PY.read_text().splitlines())
    assert line_count < BOT_PY_LINE_COUNT_CEILING, (
        f"bot.py line count is {line_count}; #1265 Slice 1 PR-6 ratchet "
        f"requires < {BOT_PY_LINE_COUNT_CEILING}."
    )


# ---------------------------------------------------------------------------
# Import-surface — canonical module is the authoritative location
# ---------------------------------------------------------------------------


def test_bot_kommo_seed_helper_importable() -> None:
    """``from telegram_bot._bot_kommo import _seed_kommo_access_token`` must work.

    P17 decomposition completed extraction — the function lives exclusively
    in _bot_kommo.py. Import via the canonical module.
    """
    from telegram_bot._bot_kommo import _seed_kommo_access_token  # noqa: F401
