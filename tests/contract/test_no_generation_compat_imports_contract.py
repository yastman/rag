"""Contract: bot-local generation compatibility shims must stay collapsed (#3222).

After #3208 (Telegram free-text converged on assistant-core) and #3216 (agent
facade removed), the bot-local generation stack in
``telegram_bot/services/generation/`` had zero production callers: the live
path is ONE ``src.core.assistant`` → ``src.runtime.pipeline`` →
``src.runtime.generation.generate_answer`` call plus Telegram presentation.
#3222 deleted the compat shims.

Bug class: dead-compat-shim-regrowth/import-of-deleted-module
Canonical issue: #3222

This contract pins the collapse:

1. The bot-local generation modules are gone from the tree:
   ``generate_response.py``, ``_stream_execution.py``,
   ``_streaming_context.py``, ``_response_formatting.py``.
2. ``telegram_formatting.py`` (Telegram-only presentation/HTML) remains —
   it is intentionally preserved delivery formatting, not generation.
3. No production module (``telegram_bot/``, ``src/``, ``scripts/``) imports
   the deleted modules, so the shims cannot silently regrow.
4. ``telegram_bot.services`` no longer re-exports ``generate_response`` /
   ``GenerationDeps``.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

GENERATION_PACKAGE = REPO_ROOT / "telegram_bot" / "services" / "generation"

REMOVED_MODULES: tuple[str, ...] = (
    "generate_response.py",
    "_stream_execution.py",
    "_streaming_context.py",
    "_response_formatting.py",
)

REMOVED_STEMS: frozenset[str] = frozenset(
    {"generate_response", "_stream_execution", "_streaming_context", "_response_formatting"}
)

FORBIDDEN_EXPORTS: tuple[str, ...] = ("generate_response", "GenerationDeps")

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


def _compat_imports_in_file(path: Path, root_name: str) -> list[str]:
    """Return imports of the deleted generation-compat modules found in *path*.

    Absolute ``telegram_bot.services.generation.<removed>`` imports are
    forbidden everywhere. Relative ``.generation.<removed>`` imports are
    flagged only inside the ``telegram_bot`` package.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return []

    offenders: list[str] = []

    def _is_removed(full: str) -> bool:
        parts = full.split(".")
        return (
            len(parts) >= 4
            and parts[-2] == "generation"
            and parts[-1] in REMOVED_STEMS
            and ".".join(parts[:-2]) == "telegram_bot.services"
        )

    def _is_generation_pkg(full: str) -> bool:
        return full == "telegram_bot.services.generation"

    def _is_relative_generation_pkg(module: str) -> bool:
        parts = module.split(".")
        return len(parts) >= 1 and parts[-1] == "generation"

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_removed(alias.name):
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            level = node.level or 0
            if level == 0:
                if _is_removed(module):
                    offenders.append(module)
                elif _is_generation_pkg(module):
                    names = [a.name for a in node.names if a.name in REMOVED_STEMS]
                    offenders.extend(f"{module}.{n}" for n in names)
            elif root_name == "telegram_bot":
                if _is_removed(module):
                    offenders.append(f"{'.' * level}{module}")
                elif _is_relative_generation_pkg(module) and (
                    ".services." in f".{module}."
                    or module == "generation"
                    or module.endswith(".generation")
                ):
                    names = [a.name for a in node.names if a.name in REMOVED_STEMS]
                    offenders.extend(f"{'.' * level}{module}.{n}" for n in names)
    return offenders


def test_generation_compat_modules_are_deleted() -> None:
    """The bot-local generation compat modules must not exist."""
    for name in REMOVED_MODULES:
        path = GENERATION_PACKAGE / name
        assert not path.exists(), (
            f"#3222: telegram_bot/services/generation/{name} was deleted; "
            "src/runtime/generation is the only generation owner. Do not "
            "reintroduce the bot-local shim."
        )


def test_telegram_formatting_is_preserved() -> None:
    """``telegram_formatting.py`` must remain (Telegram-only presentation)."""
    path = GENERATION_PACKAGE / "telegram_formatting.py"
    assert path.exists(), (
        "#3222 kept telegram_bot/services/generation/telegram_formatting.py as "
        "the Telegram-only presentation/HTML formatting module; deleting it "
        "requires an explicit replacement plan."
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for expected in ("format_answer_html", "format_sources_html", "send_html_messages"):
        assert expected in functions, (
            f"telegram_formatting.py lost {expected!r}; presentation helpers "
            "must stay intact (one-message delivery, #3222 non-goal)."
        )


def test_no_production_module_imports_generation_compat() -> None:
    """No telegram_bot/src/scripts module imports the deleted compat modules."""
    violations: dict[str, list[str]] = {}
    for root_name in PRODUCTION_ROOTS:
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for path in _iter_python_files(root):
            found = _compat_imports_in_file(path, root_name)
            if found:
                violations[path.relative_to(REPO_ROOT).as_posix()] = sorted(set(found))

    assert not violations, (
        "#3222: imports of the deleted bot-local generation compat modules found:\n"
        + "\n".join(f"  {f}: {imps}" for f, imps in violations.items())
        + "\nUse src.runtime.generation (generate_answer / GenerationRequest) "
        "for generation and telegram_formatting for presentation."
    )


def test_services_package_drops_generation_exports() -> None:
    """``telegram_bot.services`` must not re-export the deleted shims."""
    init_path = REPO_ROOT / "telegram_bot" / "services" / "__init__.py"
    init_text = init_path.read_text(encoding="utf-8")
    for symbol in FORBIDDEN_EXPORTS:
        assert "from .generation.generate_response import" not in init_text, (
            "telegram_bot/services/__init__.py still imports from the deleted "
            ".generation.generate_response module; remove the re-export (#3222)."
        )
        assert f'"{symbol}"' not in init_text, (
            f"telegram_bot/services/__init__.py still exports {symbol!r}; "
            "remove it now that the compat shim is deleted (#3222)."
        )
