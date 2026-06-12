"""Contract: DEPS-OBS2 keeps Langfuse optional around the core runtime."""

from __future__ import annotations

import ast
import builtins
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_RUNTIME_DIRS = [REPO_ROOT / "src" / "core", REPO_ROOT / "src" / "runtime"]


def test_core_and_runtime_do_not_import_langfuse_modules() -> None:
    missing_roots = [
        str(path.relative_to(REPO_ROOT)) for path in CORE_RUNTIME_DIRS if not path.is_dir()
    ]
    assert missing_roots == [], f"contract scan roots do not exist: {missing_roots}"

    violations: list[str] = []
    for base in CORE_RUNTIME_DIRS:
        for py_file in base.rglob("*.py"):
            rel = py_file.relative_to(REPO_ROOT)
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(rel))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "langfuse" or alias.name.startswith("langfuse."):
                            violations.append(f"{rel}:{node.lineno} imports {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    if module == "langfuse" or module.startswith("langfuse."):
                        violations.append(f"{rel}:{node.lineno} imports from {module}")
    assert violations == []


def test_langfuse_disabled_path_does_not_import_langfuse(monkeypatch) -> None:
    import src.observability as observability

    observability._reset_langfuse_client_for_tests()
    monkeypatch.setenv("LANGFUSE_ENABLED", "false")
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    real_import = builtins.__import__

    def guarded_import(name: str, *args, **kwargs):
        if name == "langfuse" or name.startswith("langfuse."):
            raise AssertionError(f"disabled Langfuse path imported {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    assert observability.initialize_langfuse(force=True) is None


def test_langfuse_default_disabled_even_when_credentials_exist(monkeypatch) -> None:
    import src.observability as observability

    observability._reset_langfuse_client_for_tests()
    monkeypatch.delenv("LANGFUSE_ENABLED", raising=False)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-test")

    constructed = False

    def fake_langfuse(**kwargs):
        nonlocal constructed
        constructed = True
        raise AssertionError("Langfuse must be disabled by default")

    monkeypatch.setattr(observability, "Langfuse", fake_langfuse)

    assert observability.initialize_langfuse(force=True) is None
    assert constructed is False
