"""Contract: RAG quality score documentation matches live scoring code.

Langfuse-backed quality score emission was removed in #2844. The remaining
scoring modules are compatibility no-ops, so an old minimum-score assertion
would require fake emissions. This contract instead pins the live inventory
in both directions and requires the documentation to declare its size.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCORING_PATHS = (
    REPO_ROOT / "src" / "observability" / "scores.py",
    REPO_ROOT / "src" / "scoring.py",
)
DOC_PATH = REPO_ROOT / "docs" / "RAG_QUALITY_SCORES.md"

_SCORE_TABLE_HEADER_RE = re.compile(r"^\s*\|\s*Score\s*\|", re.IGNORECASE)
_SCORE_ROW_RE = re.compile(r"^\s*\|\s*`([a-z][a-z0-9_]*)`\s*\|")
_ACTIVE_COUNT_RE = re.compile(r"Active emitted score count:\s*\*\*(\d+)\*\*", re.IGNORECASE)


def _collect_score_names_from_code() -> set[str]:
    """Collect literal score names from current scoring authorities."""
    names: set[str] = set()

    for path in SCORING_PATHS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                is_score_call = node.func.id == "score"
            else:
                is_score_call = (
                    isinstance(node.func, ast.Attribute) and node.func.attr == "create_score"
                )
            if not is_score_call:
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "name"
                    and isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                ):
                    names.add(keyword.value.value)

    return names


def _collect_score_names_from_doc() -> set[str]:
    lines = DOC_PATH.read_text(encoding="utf-8").splitlines()
    in_score_table = False
    names: set[str] = set()

    for line in lines:
        if _SCORE_TABLE_HEADER_RE.match(line):
            in_score_table = True
            continue
        if in_score_table and not line.strip().startswith("|"):
            in_score_table = False
            continue
        if not in_score_table:
            continue
        match = _SCORE_ROW_RE.match(line)
        if match:
            names.add(match.group(1))

    return names


def test_every_emitted_score_is_documented() -> None:
    code_names = _collect_score_names_from_code()
    doc_names = _collect_score_names_from_doc()
    missing = sorted(code_names - doc_names)
    assert not missing, (
        "docs/RAG_QUALITY_SCORES.md is missing rows for scores emitted by the "
        f"current scoring modules. Missing names: {missing}"
    )


def test_every_documented_score_is_emitted_by_code() -> None:
    code_names = _collect_score_names_from_code()
    doc_names = _collect_score_names_from_doc()
    stale = sorted(doc_names - code_names)
    assert not stale, (
        "docs/RAG_QUALITY_SCORES.md lists scores that the current scoring "
        f"modules do not emit. Stale names: {stale}"
    )


def test_documented_score_count_matches_code() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    match = _ACTIVE_COUNT_RE.search(text)
    assert match, "The score inventory must declare 'Active emitted score count: **N**'."
    assert int(match.group(1)) == len(_collect_score_names_from_code())


def test_doc_documents_current_score_write_status() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "No quality scores are currently emitted" in text
    assert "src/observability/scores.py" in text
    assert "src/scoring.py" in text
    assert "compatibility" in text.lower()
    assert "#2844" in text
