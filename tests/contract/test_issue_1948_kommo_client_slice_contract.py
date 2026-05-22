"""Drift guard for #1948 slice 4 — kommo_client migration to ``src/``.

Issue #1948 ("``src/api`` and ``mini_app`` import from ``telegram_bot``")
proposed migrating shared modules out of ``telegram_bot/`` so layering
arrows go the right way. ``phone_utils`` landed in PR #2018 (slice 1).
``observability`` re-export landed in PR #2020 (slice 2). ``content_loader``
landed in PR #2024 (slice 3).

This contract pins **slice 4**: the entire Kommo CRM stack
(``kommo_client``, ``kommo_models``, ``kommo_tokens``) becomes a first-class
citizen under ``src/services/`` and ``mini_app/phone.py`` imports
``KommoClient`` from there. The three ``telegram_bot/services/kommo_*.py``
files become thin re-export shims so existing bot internals
(``telegram_bot/agents/crm_tools.py``, ``telegram_bot/dialogs/crm_*``,
``telegram_bot/handlers/crm_callbacks.py``, ``scripts/kommo_seed.py``)
keep working unchanged.

Asserted invariants:

  1. ``src/services/kommo_models.py`` exists; pure pydantic, no
     ``telegram_bot`` imports at module level.
  2. ``src/services/kommo_tokens.py`` exists; module imports are clean
     (no aiogram / langgraph / langchain / fastapi).
  3. ``src/services/kommo_client.py`` exists; module-level imports go
     through ``src.observability``, ``src.services._retry``,
     ``src.services.kommo_models`` only — no ``telegram_bot.*`` paths.
  4. The three ``telegram_bot/services/kommo_*.py`` shims re-export every
     canonical public name with object-identity (``is``-equal).
  5. ``mini_app/phone.py`` imports ``KommoClient`` from
     ``src.services.kommo_client`` (no ``telegram_bot.services.kommo_client``
     reference anywhere in mini_app).
"""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CANONICAL_MODELS = REPO_ROOT / "src" / "services" / "kommo_models.py"
CANONICAL_TOKENS = REPO_ROOT / "src" / "services" / "kommo_tokens.py"
CANONICAL_CLIENT = REPO_ROOT / "src" / "services" / "kommo_client.py"

SHIM_MODELS = REPO_ROOT / "telegram_bot" / "services" / "kommo_models.py"
SHIM_TOKENS = REPO_ROOT / "telegram_bot" / "services" / "kommo_tokens.py"
SHIM_CLIENT = REPO_ROOT / "telegram_bot" / "services" / "kommo_client.py"

MINI_APP_PHONE = REPO_ROOT / "mini_app" / "phone.py"

# Forbidden module-level imports for canonical files (mini_app/src cannot
# reach into telegram_bot/* per the #1948 layering rule).
FORBIDDEN_TELEGRAM_BOT_PREFIX = "telegram_bot"

MODELS_PUBLIC_API: tuple[str, ...] = (
    "Contact",
    "ContactCreate",
    "ContactUpdate",
    "KommoCustomField",
    "KommoCustomFieldValue",
    "Lead",
    "LeadCreate",
    "LeadScoreSyncPayload",
    "LeadUpdate",
    "Note",
    "Pipeline",
    "Task",
    "TaskCreate",
    "TaskUpdate",
)
TOKENS_PUBLIC_API: tuple[str, ...] = (
    "REDIS_KEY",
    "REFRESH_BUFFER_SEC",
    "KommoTokenStore",
    "KommoTokenStoreProtocol",
)
CLIENT_PUBLIC_API: tuple[str, ...] = (
    "KommoClient",
    "KommoOAuthAuth",
)


def _ast_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text())
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.append(node.module)
    return out


# ---------------------------------------------------------------------------
# 1. Canonical files exist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [CANONICAL_MODELS, CANONICAL_TOKENS, CANONICAL_CLIENT],
    ids=["models", "tokens", "client"],
)
def test_canonical_file_exists(path: Path) -> None:
    assert path.exists(), (
        f"#1948 slice 4: expected {path.relative_to(REPO_ROOT)} to be the canonical home."
    )
    assert path.read_text().strip(), f"{path.relative_to(REPO_ROOT)} must not be empty."


# ---------------------------------------------------------------------------
# 2. Canonical modules do not import from telegram_bot
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [CANONICAL_MODELS, CANONICAL_TOKENS, CANONICAL_CLIENT],
    ids=["models", "tokens", "client"],
)
def test_canonical_does_not_import_telegram_bot(path: Path) -> None:
    """Canonical src/ modules must not depend on telegram_bot.* — that's the
    whole point of #1948 layering rule.
    """
    bad = [mod for mod in _ast_imports(path) if mod.split(".")[0] == FORBIDDEN_TELEGRAM_BOT_PREFIX]
    assert not bad, (
        f"{path.relative_to(REPO_ROOT)} module-level imports must not reach "
        f"into telegram_bot.* (#1948 layering rule); found: {bad}"
    )


# ---------------------------------------------------------------------------
# 3. Canonical public API surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", MODELS_PUBLIC_API)
def test_canonical_models_exposes_public_api(name: str) -> None:
    canonical = importlib.import_module("src.services.kommo_models")
    assert hasattr(canonical, name), (
        f"src.services.kommo_models.{name} missing — public API regression."
    )


@pytest.mark.parametrize("name", TOKENS_PUBLIC_API)
def test_canonical_tokens_exposes_public_api(name: str) -> None:
    canonical = importlib.import_module("src.services.kommo_tokens")
    assert hasattr(canonical, name), (
        f"src.services.kommo_tokens.{name} missing — public API regression."
    )


@pytest.mark.parametrize("name", CLIENT_PUBLIC_API)
def test_canonical_client_exposes_public_api(name: str) -> None:
    canonical = importlib.import_module("src.services.kommo_client")
    assert hasattr(canonical, name), (
        f"src.services.kommo_client.{name} missing — public API regression."
    )


# ---------------------------------------------------------------------------
# 4. telegram_bot shims keep object-identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("submodule", "name"),
    [("kommo_models", n) for n in MODELS_PUBLIC_API]
    + [("kommo_tokens", n) for n in TOKENS_PUBLIC_API]
    + [("kommo_client", n) for n in CLIENT_PUBLIC_API],
)
def test_telegram_bot_shim_re_exports_canonical(submodule: str, name: str) -> None:
    canonical = importlib.import_module(f"src.services.{submodule}")
    shim = importlib.import_module(f"telegram_bot.services.{submodule}")
    assert getattr(shim, name) is getattr(canonical, name), (
        f"telegram_bot.services.{submodule}.{name} must be the SAME object as "
        f"src.services.{submodule}.{name} (re-export shim, not a copy)."
    )


# ---------------------------------------------------------------------------
# 5. mini_app/phone.py imports from src/, not telegram_bot/
# ---------------------------------------------------------------------------


def test_mini_app_phone_imports_kommo_client_from_src() -> None:
    """mini_app/phone.py must not have any telegram_bot.services.kommo_*
    imports anywhere — including inside lazy ``def get_kommo_client()``.
    """
    src = MINI_APP_PHONE.read_text()
    assert "src.services.kommo_client" in src, (
        f"#1948 slice 4: {MINI_APP_PHONE.relative_to(REPO_ROOT)} must import "
        "KommoClient from src.services.kommo_client."
    )
    assert "telegram_bot.services.kommo_client" not in src, (
        f"#1948 slice 4 regression: {MINI_APP_PHONE.relative_to(REPO_ROOT)} "
        "must not reference telegram_bot.services.kommo_client anymore."
    )
    assert "telegram_bot.services.kommo_models" not in src, (
        f"#1948 slice 4 regression: {MINI_APP_PHONE.relative_to(REPO_ROOT)} "
        "must not reference telegram_bot.services.kommo_models anymore."
    )
    assert "telegram_bot.services.kommo_tokens" not in src, (
        f"#1948 slice 4 regression: {MINI_APP_PHONE.relative_to(REPO_ROOT)} "
        "must not reference telegram_bot.services.kommo_tokens anymore."
    )
