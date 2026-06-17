"""Contract: canonical project structure and active/archived directory map (#2633).

Pins the desired active architecture documented in
``docs/architecture/STRUCTURE.md``:

- Active directories under ``src/`` and ``telegram_bot/`` are present.
- Archived surfaces live only under ``archive/`` and are NOT imported by
  any live Python module under ``src/`` or ``telegram_bot/``.
- ``src/adapters`` does not import ``src/runtime``.
- ``src/ingestion`` does not import ``src/runtime``.

Refs #2633 (ARCH-19).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Active directories that MUST exist
# ---------------------------------------------------------------------------

REQUIRED_ACTIVE_DIRS = [
    "src/core",
    "src/runtime",
    "src/runtime/pipeline",
    "src/adapters",
    "src/adapters/embeddings",
    "src/adapters/llm",
    "src/ingestion/unified",
    "telegram_bot",
    "services/bge-m3-api",
    "services/docling",
    "services/user-base",
    "archive",
]

# ---------------------------------------------------------------------------
# Archived directories that must NOT be imported by live code
# ---------------------------------------------------------------------------

ARCHIVED_PACKAGES = [
    "archive.api",
    "archive.voice",
    "archive.mini_app",
    "archive.k8s",
]

# Live roots that must not import archived surfaces
LIVE_ROOTS = ("src", "telegram_bot")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*.py"))


def _imports_in_file(path: Path) -> set[str]:
    """Return all top-level module names imported by *path*."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            found.add(mod.split(".")[0] + ("." + mod.split(".", 1)[1] if "." in mod else ""))
            found.add(mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
    return found


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel_dir", REQUIRED_ACTIVE_DIRS)
def test_active_directory_exists(rel_dir: str) -> None:
    """Every active directory from the canonical structure map must be present."""
    path = REPO_ROOT / rel_dir
    assert path.is_dir(), (
        f"#2633: canonical active directory '{rel_dir}' is missing. "
        "Do not remove active directories without updating STRUCTURE.md and this test."
    )


@pytest.mark.parametrize("archived_pkg", ARCHIVED_PACKAGES)
def test_archived_package_not_imported_by_live_code(archived_pkg: str) -> None:
    """Live code under src/ and telegram_bot/ must not import archived packages."""
    violations: list[str] = []
    for root_name in LIVE_ROOTS:
        for path in _py_files(REPO_ROOT / root_name):
            imports = _imports_in_file(path)
            if any(imp == archived_pkg or imp.startswith(archived_pkg + ".") for imp in imports):
                violations.append(path.relative_to(REPO_ROOT).as_posix())

    assert not violations, (
        f"#2633: live code imports archived package '{archived_pkg}'. "
        f"Archive code must be dead. Offending files: {violations}"
    )


def test_src_adapters_does_not_import_src_runtime() -> None:
    """src/adapters must not import src/runtime (adapters are below runtime).

    One transitional coupling is in the allowlist below; it must shrink over
    time. Do not add new entries — fix the import direction instead.
    """
    # Transitional allowlist: adapter files that still import src.runtime.
    # Each entry must shrink as the migration progresses (#2633).
    ALLOWLIST: dict[str, list[str]] = {
        # LiteLlmProvider delegates to src.runtime.llm.create_litellm_chat_client
        # to avoid duplicating the LiteLLM client factory; migrate by moving
        # create_litellm_chat_client to src/adapters/llm/ or a shared utility.
        "src/adapters/llm/litellm_provider.py": ["src.runtime.llm"],
    }

    violations: dict[str, list[str]] = {}
    adapters_root = REPO_ROOT / "src" / "adapters"
    for path in _py_files(adapters_root):
        bad: list[str] = []
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "src.runtime" or mod.startswith("src.runtime."):
                    bad.append(mod)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "src.runtime" or alias.name.startswith("src.runtime."):
                        bad.append(alias.name)
        if bad:
            rel = path.relative_to(REPO_ROOT).as_posix()
            allowed = set(ALLOWLIST.get(rel, []))
            new_bad = [m for m in bad if m not in allowed]
            if new_bad:
                violations[rel] = new_bad

    assert not violations, (
        "#2633: src/adapters must not import src/runtime — adapters are below "
        "the runtime layer. Do not add new violations; shrink the ALLOWLIST "
        f"instead. New violations: {violations}"
    )


def test_src_ingestion_does_not_import_src_runtime() -> None:
    """src/ingestion must not import src/runtime (ingestion is parallel to runtime)."""
    violations: dict[str, list[str]] = {}
    ingestion_root = REPO_ROOT / "src" / "ingestion"
    for path in _py_files(ingestion_root):
        bad: list[str] = []
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if mod == "src.runtime" or mod.startswith("src.runtime."):
                    bad.append(mod)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "src.runtime" or alias.name.startswith("src.runtime."):
                        bad.append(alias.name)
        if bad:
            violations[path.relative_to(REPO_ROOT).as_posix()] = bad

    assert not violations, (
        "#2633: src/ingestion must not import src/runtime — ingestion is a "
        f"parallel infrastructure layer. Violations: {violations}"
    )
