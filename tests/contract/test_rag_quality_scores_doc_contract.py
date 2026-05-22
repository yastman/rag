"""Contract test: docs/RAG_QUALITY_SCORES.md stays in sync with scoring.py.

Parses telegram_bot/scoring.py via AST (no runtime imports) and extracts every
score name written to Langfuse. Compares the set against the documented table
in docs/RAG_QUALITY_SCORES.md. Fails if any score is missing from or extra in
the documentation.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCORING_PY = _REPO_ROOT / "telegram_bot" / "scoring.py"
_DOC_MD = _REPO_ROOT / "docs" / "RAG_QUALITY_SCORES.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_score_names_from_code() -> set[str]:
    """AST-parse scoring.py and return all unique score names."""
    source = _SCORING_PY.read_text()
    tree = ast.parse(source, filename=str(_SCORING_PY))

    names: set[str] = set()

    for node in ast.walk(tree):
        # 1. Direct score() calls with name=<string constant>
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "score":
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant) and isinstance(
                        kw.value.value, str
                    ):
                        names.add(kw.value.value)

        # 2. Dict literal keys assigned to `scores = {...}` (iterated via .items())
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "scores"
                    and isinstance(node.value, ast.Dict)
                ):
                    for key in node.value.keys:
                        if isinstance(key, ast.Constant) and isinstance(key.value, str):
                            names.add(key.value)

        # 3. Subscript assignments like scores["key"] = value
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "scores"
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    names.add(target.slice.value)

    return names


def _extract_score_names_from_doc() -> set[str]:
    """Parse RAG_QUALITY_SCORES.md and return score names from score tables.

    Only extracts from tables whose rows match the pattern:
    | `score_name` | type | description |
    where type is one of: numeric, boolean, categorical.
    """
    content = _DOC_MD.read_text()
    names: set[str] = set()
    # Match table rows where first column is backtick-wrapped and second is a score type
    for match in re.finditer(
        r"^\|\s*`([^`]+)`\s*\|\s*(?:numeric|boolean|categorical)\s*\|",
        content,
        re.MULTILINE,
    ):
        names.add(match.group(1))
    return names


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_score_names_in_code_match_doc():
    """All score names from scoring.py must appear in RAG_QUALITY_SCORES.md and vice versa."""
    code_scores = _extract_score_names_from_code()
    doc_scores = _extract_score_names_from_doc()

    in_code_not_doc = code_scores - doc_scores
    in_doc_not_code = doc_scores - code_scores

    errors: list[str] = []
    if in_code_not_doc:
        errors.append(
            "Scores in code but NOT in doc:\n"
            + "\n".join(f"  - {s}" for s in sorted(in_code_not_doc))
        )
    if in_doc_not_code:
        errors.append(
            "Scores in doc but NOT in code:\n"
            + "\n".join(f"  - {s}" for s in sorted(in_doc_not_code))
        )

    assert not errors, "\n\n".join(errors)


def test_code_extracts_expected_count():
    """Sanity check: scoring.py should have 60 unique score names (52 + 4 + 4)."""
    code_scores = _extract_score_names_from_code()
    assert len(code_scores) == 60, (
        f"Expected 60 score names in scoring.py, found {len(code_scores)}.\n"
        f"Names: {sorted(code_scores)}"
    )
