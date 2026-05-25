"""Contract: phase-1 shared runtime modules live under src/ (#1948 / #2045).

Issue #2045 (parent #1948) required moving five "low-risk" shared
modules out of ``telegram_bot/`` into the runtime kernel under ``src/``
so that ``src/api`` and ``mini_app`` can use them without reaching back
into the bot package. The migration was delivered across multiple PRs
between 2026-04 and 2026-05 (#2096, #2099, plus earlier scoring /
observability / phone_utils / content_loader migrations).

This contract pins the migration so a regression that re-introduces a
real implementation under ``telegram_bot/`` (instead of the thin
re-export shim) fails CI loudly. Each phase-1 module has two invariants:

1. The canonical implementation exists at ``src/**/<module>.py``.
2. The legacy ``telegram_bot/**/<module>.py`` path is a re-export shim
   — small (a docstring plus ``from src.<...> import ...`` block) and
   does not redefine the public functions or classes locally.

Refs #1948 #2045.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


# Each entry: legacy path under telegram_bot/, canonical path under src/,
# and the maximum line count we accept for a "shim" file. The cap is
# intentionally generous — observability.py keeps a small bot-transport
# helper (``create_callback_handler``) local because it depends on
# ``langfuse.langchain`` which is not part of the shared runtime.
PHASE1_MODULES: tuple[tuple[str, str, int], ...] = (
    ("telegram_bot/graph/state.py", "src/runtime/graph/state.py", 30),
    ("telegram_bot/graph/config.py", "src/runtime/graph/config.py", 30),
    ("telegram_bot/scoring.py", "src/scoring.py", 50),
    ("telegram_bot/phone_utils.py", "src/phone_utils.py", 30),
    ("telegram_bot/services/content_loader.py", "src/services/content_loader.py", 50),
    # observability.py keeps a bot-specific create_callback_handler local
    # alongside the re-exports, so the ceiling is higher.
    ("telegram_bot/observability.py", "src/observability.py", 100),
)


def _is_shim(path: Path, max_lines: int) -> tuple[bool, str]:
    """Return (is_shim, reason). A "shim" is small and contains no class
    definitions and no top-level def that has a non-trivial body."""
    if not path.exists():
        return False, f"path missing: {path}"
    text = path.read_text(encoding="utf-8")
    line_count = sum(1 for _ in text.splitlines())
    if line_count > max_lines:
        return False, f"file is {line_count} LOC (> {max_lines} ceiling); likely real impl"

    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        return False, f"unparseable: {exc}"

    # No top-level class definitions in a shim.
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            return False, f"contains class definition {node.name!r}"

    # Top-level def is allowed only if it is a trivial wrapper (e.g.
    # observability.py's create_callback_handler retained for langfuse
    # transport). Wrappers must not exceed ~30 statements.
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            stmt_count = len(node.body)
            if stmt_count > 30:
                return False, (
                    f"top-level def {node.name!r} has {stmt_count} statements "
                    f"(> 30); does not look like a thin wrapper"
                )

    return True, ""


def test_phase1_canonical_implementations_exist_under_src() -> None:
    """Each phase-1 module must have a real implementation under ``src/``."""
    missing: list[str] = []
    for _, src_path, _ in PHASE1_MODULES:
        full = REPO_ROOT / src_path
        if not full.exists():
            missing.append(src_path)

    assert not missing, (
        "Phase-1 canonical implementations missing under src/. Issue "
        "#2045 was closed on the assumption these modules live in the "
        "runtime kernel. Restore them or reopen #2045:\n  " + "\n  ".join(missing)
    )


def test_phase1_legacy_paths_are_thin_shims() -> None:
    """Legacy ``telegram_bot/`` paths must be re-export shims, not real impl."""
    offenders: list[str] = []
    for legacy_path, _src_path, max_lines in PHASE1_MODULES:
        legacy_full = REPO_ROOT / legacy_path
        is_shim, reason = _is_shim(legacy_full, max_lines)
        if not is_shim:
            offenders.append(f"  {legacy_path}: {reason}")

    assert not offenders, (
        "Phase-1 modules drifted back into telegram_bot/. Each legacy "
        "path must be a thin re-export shim that imports from the "
        "canonical home under src/. If you intentionally moved code "
        "back, reopen #2045 and update PHASE1_MODULES.\n" + "\n".join(offenders)
    )


def test_phase1_shims_re_export_from_canonical_src() -> None:
    """Each shim must import its public names from the canonical src/ path."""
    offenders: list[str] = []
    for legacy_path, src_path, _ in PHASE1_MODULES:
        legacy_full = REPO_ROOT / legacy_path
        if not legacy_full.exists():
            offenders.append(f"  {legacy_path}: missing")
            continue

        # Derive the expected ``from src.<module>`` prefix from the src path.
        # e.g. src/scoring.py -> src.scoring; src/runtime/graph/state.py
        # -> src.runtime.graph.state; src/services/content_loader.py
        # -> src.services.content_loader
        rel = src_path[len("src/") :]
        rel = rel.removesuffix(".py")
        expected_module = "src." + rel.replace("/", ".")
        text = legacy_full.read_text(encoding="utf-8")

        if f"from {expected_module} import" not in text:
            offenders.append(
                f"  {legacy_path}: expected `from {expected_module} import …`, not found"
            )

    assert not offenders, (
        "Phase-1 shims must re-export from the canonical src/ path:\n" + "\n".join(offenders)
    )
