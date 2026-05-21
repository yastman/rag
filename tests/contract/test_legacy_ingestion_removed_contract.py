***REMOVED*** tests/contract/test_legacy_ingestion_removed_contract.py
"""Contract: legacy ingestion modules listed in ***REMOVED***1532 must be removed and
their per-file Ruff ignores must be cleaned from ``pyproject.toml``.

Issue ***REMOVED***1532 (https://github.com/yastman/rag/issues/1532) lists three legacy
files claimed to be "replaced by the unified pipeline" (`src/ingestion/unified/`):

    - src/ingestion/docling_client.py
    - src/ingestion/gdrive_flow.py
    - src/ingestion/service.py

In addition, ``pyproject.toml`` carries per-file Ruff ignores for these paths
that need to disappear once the modules are gone.

Audit (2026-05-21) — actual repository state:

    | File | Status |
    |------|--------|
    | ``src/ingestion/gdrive_flow.py`` | Already removed (see ***REMOVED***1793). |
    | ``src/ingestion/docling_client.py`` | **STILL LIVE.** Imported by `src/ingestion/docling_native.py` (`NativeDoclingAdapter` subclasses `DoclingClient`) and by `src/ingestion/unified/targets/qdrant_hybrid_target.py` (the unified pipeline itself uses `DoclingClient` / `DoclingConfig`). |
    | ``src/ingestion/service.py`` | **STILL LIVE.** Imported by `telegram_bot/services/ingestion_cocoindex.py`, which re-exports `IngestionService`, `IngestionStats`, `ingest_from_directory`, `ingest_from_gdrive`, `get_ingestion_status` as the bot's CLI entrypoint (`python -m telegram_bot.services.ingestion_cocoindex`). |

Per-file Ruff ignores in ``pyproject.toml`` (line 269-270) declare
``ASYNC240`` for ``docling_client.py`` and ``service.py``, but ``ASYNC240``
is *also* in the global ``ignore`` list (line 252), so the per-file entries
are redundant and can be removed without touching the modules themselves.

This contract test therefore enforces three layers:

1.  ``gdrive_flow.py`` must remain absent (regression guard).
2.  Per-file Ruff ignores for the three paths must be absent from
    ``pyproject.toml`` — safe because ``ASYNC240`` is globally ignored.
3.  No non-test runtime module under ``src/`` (excluding deprecated shims),
    ``telegram_bot/``, ``mini_app/``, ``services/``, or ``scripts/`` may
    import any of the three modules. The two known live callers are tracked
    via `xfail` markers so this contract documents the blocker without
    breaking CI; once the live callers are migrated to the unified pipeline,
    the `xfail` markers must be removed.

Cross-refs:
    - ***REMOVED***1532 — original issue.
    - ***REMOVED***1793 — already removed `gdrive_flow.py` and orphaned tests.
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

***REMOVED*** Module names (importable form) used by the AST walker below.
LEGACY_DOTTED_MODULES: tuple[str, ...] = (
    "src.ingestion.docling_client",
    "src.ingestion.gdrive_flow",
    "src.ingestion.service",
)

***REMOVED*** Roots scanned for runtime imports of the legacy modules. Tests are excluded
***REMOVED*** (each test file may be migrated/removed independently).
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
    if module_path in {"src/ingestion/docling_client.py", "src/ingestion/service.py"}:
        pytest.xfail(
            f"{module_path} cannot be deleted yet: live runtime callers exist. "
            "See module docstring for the audit (DoclingClient is reused by "
            "src/ingestion/docling_native.py and src/ingestion/unified/targets/"
            "qdrant_hybrid_target.py; service.py is re-exported by "
            "telegram_bot/services/ingestion_cocoindex.py). Migrate those "
            "callers to the unified pipeline first, then drop this xfail."
        )
    assert not target.exists(), (
        f"{module_path} still exists; ***REMOVED***1532 requires it to be removed "
        "(replaced by src/ingestion/unified/)."
    )


@pytest.mark.parametrize("module_path", LEGACY_MODULES)
def test_pyproject_has_no_per_file_ignore_for_legacy_module(module_path: str) -> None:
    """``pyproject.toml`` must not list the legacy module under
    ``[tool.ruff.lint.per-file-ignores]``.

    Safe to assert even while the module file exists, because every rule
    currently pinned per-file (``ASYNC240``) is also in the global
    ``[tool.ruff.lint] ignore`` list.
    """
    pyproject_path = REPO_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    per_file = (
        data.get("tool", {})
        .get("ruff", {})
        .get("lint", {})
        .get("per-file-ignores", {})
    )
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
            ***REMOVED*** Skip vendored or virtualenv stuff, just in case.
            parts = py_file.parts
            if any(p in {".venv", "venv", "__pycache__"} for p in parts):
                continue
            ***REMOVED*** Skip files that are themselves tests.
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


***REMOVED*** Files that the audit identified as live runtime callers. Each one is xfail'd
***REMOVED*** with the precise reason so the contract documents *why* the assertion can't
***REMOVED*** pass yet.
KNOWN_LIVE_CALLERS: dict[str, str] = {
    "src/ingestion/docling_native.py": (
        "NativeDoclingAdapter subclasses DoclingClient and reuses DoclingChunk "
        "/ DoclingConfig. The unified ingestion pipeline depends on it."
    ),
    "src/ingestion/unified/targets/qdrant_hybrid_target.py": (
        "QdrantHybridTargetConnector — the *unified* pipeline target itself — "
        "imports DoclingClient and DoclingConfig directly. The premise of "
        "***REMOVED***1532 (\"replaced by unified pipeline\") does not hold for this file."
    ),
    "telegram_bot/services/ingestion_cocoindex.py": (
        "Telegram bot CLI entrypoint re-exports IngestionService, "
        "IngestionStats, ingest_from_directory, ingest_from_gdrive, "
        "get_ingestion_status from src.ingestion.service. Wired into the "
        "Makefile via `python -m telegram_bot.services.ingestion_cocoindex`."
    ),
    ***REMOVED*** The package __init__ self-references its own deprecation shims via
    ***REMOVED*** string targets; those go through importlib at attribute-access time and
    ***REMOVED*** are not real `import` statements, but they still pin the legacy modules
    ***REMOVED*** as part of the public deprecated surface (see _DEPRECATED_EXPORTS in
    ***REMOVED*** src/ingestion/__init__.py).
    "src/ingestion/__init__.py": (
        "src.ingestion declares deprecation shims pointing at "
        "src.ingestion.docling_client and src.ingestion.service in "
        "_DEPRECATED_EXPORTS. The shims emit DeprecationWarning at access "
        "time. They can only be removed once the underlying modules are "
        "gone (i.e. after the live callers above are migrated)."
    ),
}


def test_no_runtime_imports_of_legacy_ingestion_modules() -> None:
    """No production runtime module may import the three legacy ingestion modules.

    Every violation found is reported. Known live callers are surfaced as a
    soft `xfail`, so this test stays green in CI while documenting the
    pending migration. Any *new* caller of the legacy modules will fail this
    test loudly.
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

    ***REMOVED*** If we got here, every violation was an already-documented live caller.
    if findings:
        pytest.xfail(
            "Documented live callers still import legacy ingestion modules. "
            "These are tracked in KNOWN_LIVE_CALLERS in this contract test "
            "and must be migrated to the unified pipeline before the legacy "
            "modules can be deleted (***REMOVED***1532). Current callers:\n"
            + "\n".join(
                f"  {rel}: {KNOWN_LIVE_CALLERS[rel]}" for rel in sorted(findings)
            )
        )


***REMOVED*** Keep a separate, structural assertion that is independent of the imports
***REMOVED*** walker above: the existing contract guard for the gdrive_flow surface
***REMOVED*** already asserts deletion, so re-asserting here would be redundant. We
***REMOVED*** intentionally don't duplicate it — see
***REMOVED*** tests/contract/test_no_deprecated_gdrive_ingestion.py for the gdrive_flow
***REMOVED*** regression guard.


_ISSUE_LINK_RE = re.compile(r"***REMOVED***1532")


def test_contract_links_to_issue() -> None:
    """Sanity check: the contract module references its tracking issue."""
    assert _ISSUE_LINK_RE.search(Path(__file__).read_text(encoding="utf-8"))
