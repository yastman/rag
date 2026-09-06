# tests/contract/test_legacy_ingestion_removed_contract.py
"""Contract: legacy ingestion modules listed in #1532 must stay removed and
their per-file Ruff ignores must stay out of ``pyproject.toml``.

Issue #1532 (https://github.com/yastman/rag/issues/1532) listed three legacy
files claimed to be "replaced by the unified pipeline" (`src/ingestion/unified/`):

    - src/ingestion/docling_client.py
    - src/ingestion/gdrive_flow.py
    - src/ingestion/service.py

All three are absent from the tracked tree: ``gdrive_flow.py`` was removed
by #1793, and ``docling_client.py`` / ``service.py`` were removed by #3288
(the #3235 delivery — production ingestion is Markdown-only; the canonical
Markdown-only invariants live in
``tests/contract/test_markdown_only_ingestion_contract.py``). ``pyproject.toml``
must not carry per-file Ruff ignores for these paths either; the stale
comment claiming the modules still had live runtime callers was removed by
#3484.

This contract test therefore enforces three layers:

1.  All three modules must remain absent (regression guard).
2.  Per-file Ruff ignores for the three paths must stay absent from
    ``pyproject.toml`` — safe because ``ASYNC240`` is globally ignored.
3.  No non-test runtime module under ``src/``, ``telegram_bot/``,
    ``mini_app/``, ``services/``, or ``scripts/`` may import any of the
    three modules. Any new caller of the legacy modules will fail this
    test loudly.

Cross-refs:
    - #1532 — original issue.
    - #1793 — removed `gdrive_flow.py` and orphaned tests.
    - #3288 — removed the Docling/legacy ingestion implementation (#3235).
    - #3484 — removed the stale tombstones describing the deleted modules
      as live.
    - `tests/contract/test_no_deprecated_gdrive_ingestion.py` — sibling
      contract for the gdrive_flow / gdrive_indexer surface.
"""

from __future__ import annotations

import ast
import re
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]

LEGACY_MODULES: tuple[str, ...] = (
    "src/ingestion/docling_client.py",
    "src/ingestion/gdrive_flow.py",
    "src/ingestion/service.py",
)

# Module names (importable form) used by the AST walker below.
LEGACY_DOTTED_MODULES: tuple[str, ...] = (
    "src.ingestion.docling_client",
    "src.ingestion.gdrive_flow",
    "src.ingestion.service",
)

# Roots scanned for runtime imports of the legacy modules. Tests are excluded
# (each test file may be migrated/removed independently).
RUNTIME_ROOTS: tuple[str, ...] = (
    "src",
    "telegram_bot",
    "mini_app",
    "services",
    "scripts",
)


@pytest.mark.parametrize("module_path", LEGACY_MODULES)
def test_legacy_ingestion_module_is_absent(module_path: str) -> None:
    """Each legacy ingestion module file must be deleted from the repository."""
    target = REPO_ROOT / module_path
    assert not target.exists(), (
        f"{module_path} still exists; #1532 requires it to be removed "
        "(replaced by src/ingestion/unified/)."
    )


@pytest.mark.parametrize("module_path", LEGACY_MODULES)
def test_pyproject_has_no_per_file_ignore_for_legacy_module(module_path: str) -> None:
    """``pyproject.toml`` must not list the legacy module under
    ``[tool.ruff.lint.per-file-ignores]``.

    Safe to assert permanently, because the only rule ever pinned per-file
    for these paths (``ASYNC240``) is also in the global
    ``[tool.ruff.lint] ignore`` list.
    """
    pyproject_path = REPO_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    per_file = data.get("tool", {}).get("ruff", {}).get("lint", {}).get("per-file-ignores", {})
    assert module_path not in per_file, (
        f"pyproject.toml still has a per-file Ruff ignore for {module_path!r}: "
        f"{per_file[module_path]!r}. Remove it — the rules are already in the "
        "global ignore list."
    )


def _iter_runtime_python_files() -> Iterator[Path]:
    """Yield every non-test ``*.py`` file under the runtime roots."""
    for root_name in RUNTIME_ROOTS:
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for py_file in root.rglob("*.py"):
            # Skip vendored or virtualenv stuff, just in case.
            parts = py_file.parts
            if any(p in {".venv", "venv", "__pycache__"} for p in parts):
                continue
            # Skip files that are themselves tests.
            if py_file.name.startswith("test_") or py_file.name.endswith("_test.py"):
                continue
            yield py_file


def _module_imports_legacy(py_file: Path) -> set[str]:
    """Return the set of legacy dotted module names imported by ``py_file``."""
    try:
        source = py_file.read_text(encoding="utf-8")
    except OSError:
        return set()
    try:
        tree = ast.parse(source, filename=str(py_file))
    except SyntaxError:
        return set()

    hits: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in LEGACY_DOTTED_MODULES:
                hits.add(mod)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in LEGACY_DOTTED_MODULES:
                    hits.add(alias.name)
    return hits


# Files that the audit identified as live runtime callers. Empty since
# phase_6508bc74ca4a: docling_client.py deleted, callers migrated to
# docling_common.py / NativeDoclingAdapter standalone.
KNOWN_LIVE_CALLERS: dict[str, str] = {}


def test_no_runtime_imports_of_legacy_ingestion_modules() -> None:
    """No production runtime module may import the three legacy ingestion modules.

    Every violation found is reported. A caller listed in
    ``KNOWN_LIVE_CALLERS`` (empty today) would be surfaced as a soft
    `xfail`; any *new* caller of the legacy modules will fail this test
    loudly.
    """
    findings: dict[str, set[str]] = {}
    for py_file in _iter_runtime_python_files():
        hits = _module_imports_legacy(py_file)
        if not hits:
            continue
        rel = str(py_file.relative_to(REPO_ROOT))
        findings[rel] = hits

    unexpected: dict[str, set[str]] = {
        rel: hits for rel, hits in findings.items() if rel not in KNOWN_LIVE_CALLERS
    }

    if unexpected:
        formatted = "\n".join(
            f"  {rel}: imports {sorted(hits)}" for rel, hits in sorted(unexpected.items())
        )
        pytest.fail(
            "Unexpected runtime imports of legacy ingestion modules detected:\n"
            f"{formatted}\n"
            "Either migrate the caller to the unified pipeline or, if the "
            "import is truly required for now, add it to KNOWN_LIVE_CALLERS "
            "in this contract test with a clear migration note."
        )

    # If we got here, every violation was an already-documented live caller.
    if findings:
        pytest.xfail(
            "Documented live callers still import legacy ingestion modules. "
            "These are tracked in KNOWN_LIVE_CALLERS in this contract test "
            "and must be migrated to the unified pipeline before the legacy "
            "modules can be deleted (#1532). Current callers:\n"
            + "\n".join(f"  {rel}: {KNOWN_LIVE_CALLERS[rel]}" for rel in sorted(findings))
        )


# Keep a separate, structural assertion that is independent of the imports
# walker above: the existing contract guard for the gdrive_flow surface
# already asserts deletion, so re-asserting here would be redundant. We
# intentionally don't duplicate it — see
# tests/contract/test_no_deprecated_gdrive_ingestion.py for the gdrive_flow
# regression guard.


_ISSUE_LINK_RE = re.compile(r"#1532")


def test_contract_links_to_issue() -> None:
    """Sanity check: the contract module references its tracking issue."""
    assert _ISSUE_LINK_RE.search(Path(__file__).read_text(encoding="utf-8"))
