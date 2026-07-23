"""Gate: core/runtime must not import create_agent from langchain.agents.

The ADR-0019 doc at docs/adr/0019-core-text-path-procedural-runtime.md was
removed along with the adr/ directory — but the architectural constraint that
keeps create_agent in adapter/conversational shells remains enforced.
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_RUNTIME_ROOTS = (REPO_ROOT / "src" / "core", REPO_ROOT / "src" / "runtime")


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in CORE_RUNTIME_ROOTS:
        files.extend(path for path in root.rglob("*.py") if path.is_file())
    return files


def test_core_runtime_does_not_import_create_agent() -> None:
    offenders: list[str] = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                imported_names = {alias.name for alias in node.names}
                if node.module == "langchain.agents" and "create_agent" in imported_names:
                    offenders.append(str(path.relative_to(REPO_ROOT)))
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "langchain.agents.create_agent":
                        offenders.append(str(path.relative_to(REPO_ROOT)))

    assert not offenders, (
        "ADR-0019 keeps create_agent in adapter/conversational shells, not the "
        f"core runtime text path. Offenders: {offenders}"
    )
