"""Regression guard for removed KFP/Kubernetes dependencies (#2450)."""

from __future__ import annotations

import ast
import re
import tomllib
from pathlib import Path


PYPROJECT = Path("pyproject.toml")
LOCKFILE = Path("uv.lock")
RUNTIME_ROOTS = [Path("src"), Path("telegram_bot")]
FORBIDDEN = {"kfp", "kfp-kubernetes", "kfp-pipeline-spec", "kfp-server-api", "kubernetes"}


def _dependency_names() -> set[str]:
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    names: set[str] = set()

    def add(deps: list[str]) -> None:
        for dep in deps:
            match = re.match(r"([A-Za-z0-9_.-]+)", dep)
            assert match, f"Could not parse dependency {dep!r}"
            names.add(match.group(1).lower().replace("_", "-"))

    add(project["project"].get("dependencies", []))
    for deps in project["project"].get("optional-dependencies", {}).values():
        add(deps)
    for deps in project.get("dependency-groups", {}).values():
        add(deps)
    return names


def test_kfp_kubernetes_are_not_declared_dependencies() -> None:
    assert _dependency_names().isdisjoint(FORBIDDEN)


def test_kfp_kubernetes_are_not_locked() -> None:
    text = LOCKFILE.read_text(encoding="utf-8")
    for package in FORBIDDEN:
        assert f'name = "{package}"' not in text


def test_runtime_code_does_not_import_kfp_or_kubernetes() -> None:
    offenders: list[str] = []
    for root in RUNTIME_ROOTS:
        for path in root.rglob("*.py"):
            if any(part in {".venv", "__pycache__"} for part in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = {alias.name.split(".", 1)[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = {node.module.split(".", 1)[0]}
                else:
                    continue
                if names & {"kfp", "kubernetes"}:
                    offenders.append(f"{path}:{node.lineno}")
    assert not offenders
