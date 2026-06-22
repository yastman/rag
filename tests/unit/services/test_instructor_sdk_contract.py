"""Contracts ensuring active structured-output paths do not use Instructor (#2429)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
PROD_ROOTS = (
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "src",
)


ACTIVE_STRUCTURED_OUTPUT_PATHS = [
    REPO_ROOT / "telegram_bot" / "services" / "apartment_llm_extractor.py",
    REPO_ROOT / "telegram_bot" / "services" / "query_analyzer.py",
    REPO_ROOT / "src" / "evaluation" / "generate_test_queries.py",
]


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in PROD_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in {".venv", "node_modules", "build", "dist"} for part in path.parts):
                continue
            files.append(path)
    return files


def _calls_in(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


@pytest.mark.parametrize("path", _iter_python_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_no_instructor_streaming_primitives_in_production(path: Path) -> None:
    """No active production code should reintroduce Instructor streaming primitives."""
    source = path.read_text(encoding="utf-8")
    if "create_partial" not in source and "create_iterable" not in source:
        return

    tree = ast.parse(source, filename=str(path))
    forbidden_attrs = {"create_partial", "create_iterable"}
    offenders: list[str] = []
    for call in _calls_in(tree):
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr in forbidden_attrs:
            offenders.append(f"line {call.lineno}: .{func.attr}(...)")
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)}: Instructor streaming primitive(s) detected: "
        f"{offenders}. Structured output must use the LiteLLM SDK router JSON-schema path."
    )


@pytest.mark.parametrize(
    "path", ACTIVE_STRUCTURED_OUTPUT_PATHS, ids=lambda p: str(p.relative_to(REPO_ROOT))
)
def test_active_structured_output_paths_do_not_import_instructor(path: Path) -> None:
    """Structured output call sites should use LiteLLM/OpenAI-compatible JSON schema."""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders.extend(alias.name for alias in node.names if alias.name == "instructor")
        elif isinstance(node, ast.ImportFrom) and node.module == "instructor":
            offenders.append(f"disallowed SDK import at line {node.lineno}")
    assert not offenders, (
        f"{path.relative_to(REPO_ROOT)} imports Instructor: {offenders}. "
        "Use src.runtime.llm.create_litellm_chat_client(..., response_model=...) instead."
    )
    assert "instructor." + "from_openai" not in source
    assert "instructor." + "from_provider" not in source
