"""Error-level span contract tests (AST-based, no Docker needed).

Verifies that ERROR/WARNING span updates only appear in allowed locations.
"""

import ast
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).parent.parent.parent

SCAN_DIRS = [
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "src",
]
EXCLUDE_DIRS = ["tests/", ".venv/"]

# Only these files are permitted to call update_current_span(level="ERROR"/"WARNING")
ERROR_SPAN_ALLOWLIST: dict[str, list[str]] = {
    # Graph nodes — core pipeline error/fallback paths
    "telegram_bot/graph/nodes/generate.py": ["ERROR", "WARNING"],
    "telegram_bot/graph/nodes/rewrite.py": ["ERROR"],
    "telegram_bot/graph/nodes/rerank.py": ["ERROR"],
    "telegram_bot/graph/nodes/respond.py": ["ERROR"],
    "telegram_bot/graph/nodes/cache.py": ["ERROR"],
    # Agent tools — pipeline wrapper error paths
    "telegram_bot/agents/rag_tool.py": ["ERROR"],
    "telegram_bot/agents/history_tool.py": ["ERROR"],
    "telegram_bot/agents/rag_pipeline.py": ["ERROR"],
    "telegram_bot/agents/history_graph/nodes.py": ["ERROR"],
    # Services — curated error spans for degraded operations
    "telegram_bot/integrations/cache.py": ["ERROR", "WARNING"],
    "telegram_bot/services/generate_response.py": ["ERROR", "WARNING"],
    "telegram_bot/services/qdrant.py": ["ERROR", "WARNING"],
    "telegram_bot/services/history_service.py": ["ERROR"],
    "telegram_bot/middlewares/error_handler.py": ["ERROR"],
}


def _collect_error_span_calls(
    directories: list[Path],
    exclude_dirs: list[str] | None = None,
) -> list[dict]:
    """Return list of {file, line, level} for update_current_span(level=ERROR/WARNING) calls."""
    found = []
    exclude = set(exclude_dirs or [])
    for directory in directories:
        if not directory.exists():
            continue
        for py_file in directory.rglob("*.py"):
            if any(ex in str(py_file) for ex in exclude):
                continue
            try:
                tree = ast.parse(py_file.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                is_update = (
                    isinstance(func, ast.Attribute) and func.attr == "update_current_span"
                ) or (isinstance(func, ast.Name) and func.id == "update_current_span")
                if not is_update:
                    continue
                kwargs = {kw.arg: kw.value for kw in node.keywords}
                level_node = kwargs.get("level")
                if not isinstance(level_node, ast.Constant):
                    continue
                level_value = level_node.value
                if level_value not in ("ERROR", "WARNING"):
                    continue
                found.append(
                    {
                        "file": py_file,
                        "rel_path": str(py_file.relative_to(REPO_ROOT)),
                        "line": node.lineno,
                        "level": level_value,
                    }
                )
    return found


def _collect_python_files(
    directories: list[Path],
    exclude_dirs: list[str] | None = None,
) -> list[Path]:
    """Return all .py files in scan dirs, excluding specified paths."""
    files = []
    exclude = set(exclude_dirs or [])
    for directory in directories:
        if not directory.exists():
            continue
        for py_file in directory.rglob("*.py"):
            if any(ex in str(py_file) for ex in exclude):
                continue
            files.append(py_file)
    return files


def test_error_spans_only_in_allowed_locations() -> None:
    """update_current_span(level=ERROR/WARNING) must only appear in allowlisted files."""
    calls = _collect_error_span_calls(SCAN_DIRS, EXCLUDE_DIRS)

    violations = []
    for call in calls:
        rel = call["rel_path"]
        level = call["level"]
        allowed_levels = ERROR_SPAN_ALLOWLIST.get(rel)
        if allowed_levels is None:
            violations.append(
                f"  {rel}:{call['line']} — level={level!r} not in allowlist. "
                f"Add to ERROR_SPAN_ALLOWLIST or remove the ERROR span."
            )
        elif level not in allowed_levels:
            violations.append(
                f"  {rel}:{call['line']} — level={level!r} not allowed for this file "
                f"(allowed: {allowed_levels}). Update ERROR_SPAN_ALLOWLIST."
            )

    assert not violations, "ERROR/WARNING span calls found outside allowlist:\n" + "\n".join(
        violations
    )


@pytest.mark.parametrize("py_file", _collect_python_files(SCAN_DIRS, EXCLUDE_DIRS))
def test_no_bare_level_error_strings(py_file: Path) -> None:
    """Backup check: no raw 'level="ERROR"' strings outside AST-visible span updates.

    Catches ERROR spans in string templates, dict literals, or other non-call contexts.
    """
    rel = str(py_file.relative_to(REPO_ROOT))
    allowed_levels = ERROR_SPAN_ALLOWLIST.get(rel, [])

    content = py_file.read_text()
    matches = re.findall(r'level\s*=\s*["\']ERROR["\']', content)

    if matches and "ERROR" not in allowed_levels:
        pytest.fail(
            f"{rel}: found {len(matches)} raw 'level=\"ERROR\"' occurrence(s) "
            f"but file is not in ERROR_SPAN_ALLOWLIST. "
            f"Either add to allowlist or use a different mechanism."
        )


def test_error_allowlist_files_exist() -> None:
    """All files in ERROR_SPAN_ALLOWLIST must exist in the repository."""
    missing = []
    for rel_path in ERROR_SPAN_ALLOWLIST:
        full_path = REPO_ROOT / rel_path
        if not full_path.exists():
            missing.append(f"  {rel_path}")

    assert not missing, (
        "ERROR_SPAN_ALLOWLIST references non-existent files:\n"
        + "\n".join(missing)
        + "\nUpdate ERROR_SPAN_ALLOWLIST in tests/contract/test_error_contract.py."
    )
