"""Contract: production ``src`` modules must not import test code (#2491)."""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"


def test_src_modules_do_not_import_tests_package() -> None:
    violations: dict[str, list[str]] = {}
    for path in sorted(SRC_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "tests" or module.startswith("tests."):
                    modules.add(module)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name
                    if name == "tests" or name.startswith("tests."):
                        modules.add(name)
        if modules:
            violations[path.relative_to(REPO_ROOT).as_posix()] = sorted(modules)

    assert not violations, f"Production src modules must not import tests: {violations}"
