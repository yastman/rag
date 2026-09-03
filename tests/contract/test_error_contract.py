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
EXCLUDE_DIRS = ("tests", ".venv")

# Only these files are permitted to call update_current_span(level="ERROR"/"WARNING")
ERROR_SPAN_ALLOWLIST: dict[str, list[str]] = {
    # Voice transcription error path (Whisper / LiteLLM failure) — span is
    # re-raised so the outer voice-session trace records the failure (#1810).
    "src/runtime/graph/nodes/transcribe.py": ["ERROR"],
    # Services — curated error spans for degraded operations
    "telegram_bot/integrations/cache.py": ["ERROR", "WARNING"],
    "src/runtime/integrations/cache.py": ["ERROR", "WARNING"],
    "telegram_bot/services/qdrant.py": ["ERROR", "WARNING"],
    "src/runtime/services/qdrant.py": ["ERROR", "WARNING"],
    # SDK-native runtime pipeline — curated ERROR spans on the embedding,
    # rerank (ColBERT) and rewrite (LLM) failure paths inside ``except``
    # blocks; mirrors the telegram_bot pipeline counterparts (core migration).
    "src/runtime/pipeline/rag.py": ["ERROR"],
    # Stage files extracted from rag.py in #2900 — inherit same ERROR span policy.
    "src/runtime/pipeline/_cache_stage.py": ["ERROR"],
    "src/runtime/pipeline/_grade_rerank.py": ["ERROR"],
    "src/runtime/pipeline/_rewrite_cache.py": ["ERROR"],
    # SDK-native query preprocessor — ERROR spans on the HyDE generation
    # API-failure paths (CORE-023 move from telegram_bot.services).
    "src/runtime/services/query_preprocessor.py": ["ERROR"],
    # SDK-native generation service — ERROR span on the LLM-failure fallback
    # path (CORE-004 split). Bot-local generate_response.py removed in #3222.
    "src/runtime/generation/service.py": ["ERROR"],
    "telegram_bot/middlewares/error_handler.py": ["ERROR"],
    # CRM callback handlers — archived in #2625 (CRM archival).
    # "telegram_bot/handlers/crm_callbacks.py": ["ERROR"],
    # CRM quick-actions aiogram-dialog — archived in #2625.
    # "telegram_bot/dialogs/crm_quick_actions.py": ["ERROR"],
    # Background scheduler jobs — hot_lead_notifier archived in #2625.
    # NOTE: lead_score_sync, nurturing_scheduler, session_summary_worker archived in #2602.
    # "telegram_bot/services/hot_lead_notifier.py": ["ERROR"],
    # Qdrant conversation-history service removed in #3214.
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
            rel_path = py_file.relative_to(REPO_ROOT)
            if not exclude.isdisjoint(rel_path.parts):
                continue
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8"))
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
            if not exclude.isdisjoint(py_file.relative_to(REPO_ROOT).parts):
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

    content = py_file.read_text(encoding="utf-8")
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
