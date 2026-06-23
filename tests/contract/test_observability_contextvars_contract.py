"""Observability contextvars propagation contract tests.

This guardrail blocks the recurring Langfuse / OTEL / contextvars bug class:
raw thread or executor boundaries can drop the parent trace context and create
orphaned spans. The scanner is AST-based and does not need Docker.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS: tuple[Path, ...] = (
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "src",
)
EXCLUDE_DIRS: tuple[str, ...] = ("/tests/", "/.venv/", "/__pycache__/")

CONTEXT_BREAKING_ALLOWLIST: dict[str, str] = {
    "src/voice/agent.py:619": (
        "Standalone local health-check HTTP server thread. It does not carry "
        "request/RAG observability context and does not create child Langfuse spans."
    ),
}


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for directory in SCAN_DIRS:
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            path_str = str(path)
            if any(fragment in path_str for fragment in EXCLUDE_DIRS):
                continue
            files.append(path)
    return files


def _callable_name(func: ast.AST) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _extract_callable_arg(call_node: ast.Call, pattern: str) -> ast.AST | None:
    if pattern == "loop.run_in_executor":
        if len(call_node.args) >= 2:
            return call_node.args[1]
        for kw in call_node.keywords:
            if kw.arg == "func":
                return kw.value
        return None

    if pattern == "threading.Thread":
        for kw in call_node.keywords:
            if kw.arg == "target":
                return kw.value
        return call_node.args[0] if call_node.args else None

    if pattern == "ThreadPoolExecutor.submit":
        return call_node.args[0] if call_node.args else None

    return None


def _node_uses_context_run(node: ast.AST | None) -> bool:
    if node is None:
        return False

    candidates = list(ast.walk(node))
    candidates.append(node)
    for child in candidates:
        if isinstance(child, ast.Attribute) and child.attr == "run":
            if isinstance(child.value, ast.Name) and child.value.id in {"ctx", "context"}:
                return True
            if isinstance(child.value, ast.Call):
                func = child.value.func
                if isinstance(func, ast.Attribute) and func.attr == "copy_context":
                    return True
                if isinstance(func, ast.Name) and func.id == "copy_context":
                    return True

        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr == "run":
                if isinstance(func.value, ast.Name) and func.value.id in {"ctx", "context"}:
                    return True
                if isinstance(func.value, ast.Call):
                    value_func = func.value.func
                    if isinstance(value_func, ast.Attribute) and value_func.attr == "copy_context":
                        return True
                    if isinstance(value_func, ast.Name) and value_func.id == "copy_context":
                        return True

    return False


def _call_uses_safe_wrapper(call_node: ast.Call, pattern: str) -> bool:
    callable_arg = _extract_callable_arg(call_node, pattern)
    if _node_uses_context_run(callable_arg):
        return True

    # ``asyncio.to_thread`` propagates contextvars; it is the preferred wrapper.
    if pattern != "loop.run_in_executor":
        return False

    return False


def _collect_concurrency_sites(*, unsafe_only: bool) -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for path in _iter_python_files():
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except SyntaxError:
            continue

        lines = source.splitlines()
        rel_path = str(path.relative_to(REPO_ROOT))

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            func_name = _callable_name(node.func)
            pattern: str | None = None
            if func_name == "Thread":
                pattern = "threading.Thread"
            elif func_name == "submit":
                pattern = "ThreadPoolExecutor.submit"
            elif func_name == "run_in_executor":
                pattern = "loop.run_in_executor"

            if pattern is None:
                continue

            safe = _call_uses_safe_wrapper(node, pattern)
            if unsafe_only and safe:
                continue

            snippet = "\n".join(
                f"  {line_no + 1}: {lines[line_no]}"
                for line_no in range(max(0, node.lineno - 2), min(len(lines), node.lineno + 1))
            )
            found.append(
                {
                    "file": rel_path,
                    "line": node.lineno,
                    "pattern": pattern,
                    "safe": safe,
                    "snippet": snippet,
                }
            )

    return sorted(found, key=lambda item: (str(item["file"]), int(item["line"])))


@pytest.fixture(scope="session")
def concurrency_sites() -> list[dict[str, object]]:
    return _collect_concurrency_sites(unsafe_only=True)


@pytest.fixture(scope="session")
def all_concurrency_sites() -> list[dict[str, object]]:
    return _collect_concurrency_sites(unsafe_only=False)


def test_all_concurrency_sites_allowlisted_or_wrapped(
    concurrency_sites: list[dict[str, object]],
) -> None:
    violations: list[str] = []
    for site in concurrency_sites:
        key = f"{site['file']}:{site['line']}"
        if key in CONTEXT_BREAKING_ALLOWLIST:
            continue
        violations.append(
            f"  {site['file']}:{site['line']} -- {site['pattern']}\n"
            f"{site['snippet']}\n"
            "  ACTION: use asyncio.to_thread/contextvars.copy_context().run(...) "
            "or document a narrow allowlist rationale."
        )

    assert not violations, "Raw concurrency sites can drop Langfuse/OTEL context:\n" + "\n".join(
        violations
    )


def test_pipeline_uses_to_thread_for_observed_search() -> None:
    pipeline_file = REPO_ROOT / "src" / "core" / "pipeline.py"
    if not pipeline_file.exists():
        pytest.skip("src/core/pipeline.py not found")

    content = pipeline_file.read_text(encoding="utf-8")
    assert "asyncio.to_thread" in content, (
        "src/core/pipeline.py must use asyncio.to_thread for observed thread hops; "
        "it propagates contextvars and prevents orphan Langfuse spans."
    )
    assert "run_in_executor" not in content, (
        "src/core/pipeline.py must not use raw run_in_executor for observed search paths."
    )


def test_contextvars_allowlist_no_stale_entries(
    all_concurrency_sites: list[dict[str, object]],
) -> None:
    actual_sites = {f"{site['file']}:{site['line']}" for site in all_concurrency_sites}
    stale = [key for key in CONTEXT_BREAKING_ALLOWLIST if key not in actual_sites]
    assert not stale, "CONTEXT_BREAKING_ALLOWLIST contains stale entries:\n  " + "\n  ".join(stale)


def test_contextvars_allowlist_has_rationale() -> None:
    missing = [
        key for key, rationale in CONTEXT_BREAKING_ALLOWLIST.items() if not rationale.strip()
    ]
    assert not missing, "Allowlist entries must include rationale: " + ", ".join(missing)
