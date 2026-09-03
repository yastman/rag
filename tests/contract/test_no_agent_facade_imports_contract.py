"""Contract: the removed imperative agent facade must not be re-imported (#3216).

``telegram_bot.agents`` (ImperativeBotAgent, BotContext, the tool registry and
the agent-only tool wrappers) was an inert facade: it ignored tools, prompt,
model and checkpointer and called assistant-core directly. #3216 deleted the
package and routed Q&A plus product actions to assistant-core and the
deterministic product services.

Bug class: dead-facade-regrowth/import-of-deleted-module
Canonical issue: #3216

This contract pins the deletion:

1. The ``telegram_bot/agents`` package is gone from the tree.
2. No production module (``telegram_bot/``, ``src/``, ``scripts/``) imports
   ``telegram_bot.agents`` (absolute or relative), so the facade cannot
   silently regrow.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

FACADE_PACKAGE = "telegram_bot.agents"

# Production roots scanned for imports (mirrors Makefile LINT_PATHS).
PRODUCTION_ROOTS: tuple[str, ...] = ("telegram_bot", "src", "scripts")

_NOISE_PARTS: frozenset[str] = frozenset(
    {
        ".venv",
        "venv",
        "__pycache__",
        ".tox",
        "node_modules",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".worktrees",
        ".git",
    }
)


def _iter_python_files(root: Path):
    for dirpath, dirnames, filenames in root.walk():
        dirnames[:] = [d for d in dirnames if d not in _NOISE_PARTS]
        yield from (Path(dirpath) / name for name in sorted(filenames) if name.endswith(".py"))


def _facade_imports_in_file(path: Path, root_name: str) -> list[str]:
    """Return facade import module strings found in *path* (AST scan).

    Absolute ``telegram_bot.agents`` imports are forbidden everywhere.
    Relative ``.agents`` imports resolve to ``telegram_bot.agents`` only for
    modules inside the ``telegram_bot`` package, so they are flagged only
    there (a hypothetical ``src/.agents`` is out of scope for this contract).
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []

    offenders: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == FACADE_PACKAGE or alias.name.startswith(FACADE_PACKAGE + "."):
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level or 0
            if level == 0:
                is_facade = module == FACADE_PACKAGE or module.startswith(FACADE_PACKAGE + ".")
            elif root_name == "telegram_bot":
                is_facade = module == "agents" or module.startswith("agents.")
            else:
                is_facade = False
            if is_facade:
                offenders.append(f"{'.' * level}{module}")
    return offenders


def test_agent_facade_package_is_deleted() -> None:
    """The telegram_bot/agents package directory must not exist."""
    assert not (REPO_ROOT / "telegram_bot" / "agents").exists(), (
        "#3216: telegram_bot/agents was deleted; do not reintroduce the "
        "imperative agent facade or the inert tool registry."
    )


def test_importing_agent_facade_fails() -> None:
    """Importing the deleted facade raises ModuleError (import lock)."""
    import importlib

    try:
        importlib.import_module(FACADE_PACKAGE)
    except ImportError:
        return
    raise AssertionError(
        f"#3216: {FACADE_PACKAGE} is importable again; the deleted facade regrew."
    )


def test_no_production_module_imports_agent_facade() -> None:
    """No telegram_bot/src/scripts module imports telegram_bot.agents."""
    violations: dict[str, list[str]] = {}
    for root_name in PRODUCTION_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in _iter_python_files(root):
            found = _facade_imports_in_file(path, root_name)
            if found:
                violations[path.relative_to(REPO_ROOT).as_posix()] = sorted(set(found))

    assert not violations, (
        "#3216: imports of the deleted imperative agent facade "
        f"({FACADE_PACKAGE}) found in production code:\n"
        + "\n".join(f"  {f}: {imps}" for f, imps in violations.items())
        + "\nRoute queries via assistant-core (telegram_bot.assistant_core_adapter) "
        "or the deterministic product services instead."
    )
