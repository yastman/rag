"""Drift guard for #1265 — `_bot_postgres_bootstrap` extract.

Issue #1265 published a phased extraction plan that pulls module-level
helpers out of ``telegram_bot/bot.py`` so the ``PropertyBot`` class
shrinks to a thin facade. PR-1..PR-6 of Slice 1 already landed
(``_bot_kommo``, ``_bot_observability``, ``_bot_pre_agent``,
``_bot_state_helpers``, ``_bot_streaming``, ``_bot_error_classification``).

This contract pins the **postgres bootstrap** extract:

* ``_extract_database_name(database_url) -> str | None`` — pure URL
  parsing.
* ``async ensure_postgres_database_exists(asyncpg_module, admin_database_url,
  database_name) -> bool`` — runs ``CREATE DATABASE`` on the maintenance
  connection, idempotent, identifier-safe.
* ``async ensure_realestate_schema(pg_pool) -> None`` — applies the
  cached ``REALESTATE_SCHEMA_STATEMENTS`` list (CREATE TABLE / CREATE
  INDEX) on the live pool.
* ``REALESTATE_SCHEMA_STATEMENTS`` — module-level tuple of SQL DDL.

The class methods on ``PropertyBot`` stay (``_ensure_postgres_database_exists``,
``_ensure_realestate_schema``, ``_extract_database_name``) as thin
wrappers that bind ``self.config.realestate_database_url`` and
``self._pg_pool`` and delegate to the canonical module. Existing tests
that import via ``from telegram_bot.bot import …`` keep working.

Asserted invariants:

  1. ``telegram_bot/_bot_postgres_bootstrap.py`` exists.
  2. The module exposes ``REALESTATE_SCHEMA_STATEMENTS``,
     ``extract_database_name``, ``ensure_postgres_database_exists``,
     ``ensure_realestate_schema`` at module top.
  3. Module-level imports stay light (no aiogram / langgraph / fastapi /
     langchain / qdrant — only stdlib + ``logging`` + ``re`` +
     ``urllib.parse``).
  4. ``REALESTATE_SCHEMA_STATEMENTS`` is a tuple/list of >=10 SQL
     statements (sanity floor — we do not want a silent "extracted
     module" with no schema).
  5. ``bot.py`` keeps the static / async wrappers exactly once so
     ``bot._extract_database_name`` and ``bot._ensure_realestate_schema``
     keep resolving for existing tests.
  6. ``bot.py`` line count is strictly below the 4699 baseline this PR
     starts from. The ratchet floor moves down each extraction.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
NEW_MODULE = REPO_ROOT / "telegram_bot" / "_bot_postgres_bootstrap.py"
BOT_PY = REPO_ROOT / "telegram_bot" / "bot.py"


REQUIRED_PUBLIC_NAMES: tuple[str, ...] = (
    "REALESTATE_SCHEMA_STATEMENTS",
    "extract_database_name",
    "ensure_postgres_database_exists",
    "ensure_realestate_schema",
)


FORBIDDEN_MODULE_LEVEL_IMPORTS: tuple[str, ...] = (
    "aiogram",
    "langgraph",
    "fastapi",
    "langchain",
    "qdrant_client",
    "redis",
    "telegram_bot.bot",
)


# Strictly less than this. The ratchet shrinks each extraction; if a
# future PR adds bot.py lines without an offsetting extract, it should
# fail this contract first.
BOT_PY_LINE_COUNT_CEILING = 4699


def _module_ast() -> ast.Module:
    return ast.parse(NEW_MODULE.read_text(encoding="utf-8"))


def test_module_exists() -> None:
    assert NEW_MODULE.exists(), (
        f"Expected extracted module at "
        f"{NEW_MODULE.relative_to(REPO_ROOT)} (#1265 postgres bootstrap "
        f"slice). The file owns the canonical implementation; bot.py "
        f"keeps thin wrappers."
    )


def test_module_exposes_required_public_names() -> None:
    tree = _module_ast()
    top_names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            top_names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    top_names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            top_names.add(node.target.id)
    missing = [name for name in REQUIRED_PUBLIC_NAMES if name not in top_names]
    assert not missing, (
        f"_bot_postgres_bootstrap.py must expose {REQUIRED_PUBLIC_NAMES} "
        f"at module top; missing: {missing}."
    )


def test_module_imports_stay_light() -> None:
    tree = _module_ast()
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(
                mod == bad or mod.startswith(bad + ".") for bad in FORBIDDEN_MODULE_LEVEL_IMPORTS
            ):
                offenders.append(mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if any(
                    alias.name == bad or alias.name.startswith(bad + ".")
                    for bad in FORBIDDEN_MODULE_LEVEL_IMPORTS
                ):
                    offenders.append(alias.name)
    assert not offenders, (
        f"_bot_postgres_bootstrap.py must keep module-level imports "
        f"light (stdlib + logging + re + urllib.parse). Forbidden "
        f"top-level imports found: {offenders}."
    )


def test_realestate_schema_statements_is_a_real_schema() -> None:
    """Sanity floor: the extracted DDL must contain >=10 statements;
    a near-empty list would mean someone extracted the wrapper but lost
    the canonical schema. Ten is well below the actual count (~24)."""
    from telegram_bot import _bot_postgres_bootstrap as mod

    statements = list(mod.REALESTATE_SCHEMA_STATEMENTS)
    assert len(statements) >= 10, (
        f"REALESTATE_SCHEMA_STATEMENTS must hold the full schema; got "
        f"only {len(statements)} statements."
    )
    # Each entry is a SQL string.
    assert all(isinstance(stmt, str) and stmt.strip() for stmt in statements), (
        "REALESTATE_SCHEMA_STATEMENTS entries must be non-empty strings."
    )
    # The canonical statements include user_favorites and search_events
    # (those are the rows the extracted live tests exercise).
    joined = "\n".join(statements).lower()
    assert "user_favorites" in joined, "user_favorites table missing from schema."
    assert "search_events" in joined, "search_events table missing from schema."


def test_bot_py_keeps_wrappers_for_back_compat() -> None:
    text = BOT_PY.read_text(encoding="utf-8")
    # Static wrapper for the URL parser.
    assert "def _extract_database_name(" in text, (
        "bot.py must keep _extract_database_name as a thin wrapper so "
        "existing imports `from telegram_bot.bot import …` continue to "
        "resolve."
    )
    # Async wrapper for schema bootstrap.
    assert "async def _ensure_realestate_schema(" in text, (
        "bot.py must keep _ensure_realestate_schema as a thin wrapper so "
        "tests/unit/test_bot_handlers.py's "
        "test_ensure_realestate_schema_creates_user_favorites keeps "
        "calling through bot._ensure_realestate_schema."
    )
    # Async wrapper for database creation.
    assert "async def _ensure_postgres_database_exists(" in text, (
        "bot.py must keep _ensure_postgres_database_exists as a thin "
        "wrapper so existing call sites in PropertyBot.start() continue "
        "to resolve."
    )
    # Each wrapper appears exactly once — no accidental duplication.
    assert len(re.findall(r"def _extract_database_name\(", text)) == 1
    assert len(re.findall(r"async def _ensure_realestate_schema\(", text)) == 1
    assert len(re.findall(r"async def _ensure_postgres_database_exists\(", text)) == 1


def test_bot_py_line_count_is_below_ratchet() -> None:
    bot_lines = len(BOT_PY.read_text(encoding="utf-8").splitlines())
    assert bot_lines < BOT_PY_LINE_COUNT_CEILING, (
        f"bot.py grew above the {BOT_PY_LINE_COUNT_CEILING} ratchet "
        f"floor (current: {bot_lines}). Each extraction must shrink "
        f"bot.py — if a wrapper rewrite needed extra lines, decompose "
        f"another helper to offset it before lowering the ceiling."
    )
