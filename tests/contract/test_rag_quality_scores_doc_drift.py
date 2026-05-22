"""Contract: ``docs/RAG_QUALITY_SCORES.md`` matches ``src/scoring.py`` (#1956).

The doc enumerates every Langfuse score we emit per query. Whenever a new
``name=...`` lands in ``write_langfuse_scores``, ``write_history_scores``, or
``write_crm_scores``, the doc table must gain a corresponding row. This
contract pins parity in both directions:

* every score name emitted by the scoring module appears in the doc;
* every score name listed in the doc is actually emitted by the scoring module.

Scope:

* Source of truth (code): ``src/scoring.py``. We collect every
  string literal passed as ``name=...`` to ``score(...)`` or
  ``lf.create_score(...)``, plus every key of the always-written ``scores``
  dict literal in ``write_langfuse_scores``.
* Source of truth (doc): ``docs/RAG_QUALITY_SCORES.md``. We collect every
  backtick-wrapped identifier in the first column of any Markdown table
  whose header is ``| Score |``.

If a name is intentionally not user-facing (e.g. an internal helper), add
it to ``DOC_EXEMPT_SCORE_NAMES`` with a reason; do not silence the test by
trimming the doc.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCORING_PY = REPO_ROOT / "src" / "scoring.py"
DOC_PATH = REPO_ROOT / "docs" / "RAG_QUALITY_SCORES.md"

# Score names emitted by scoring.py that intentionally do not appear in the
# operator-facing table. Keep this set empty unless there is a documented
# reason; the goal of #1956 is parity.
DOC_EXEMPT_SCORE_NAMES: frozenset[str] = frozenset()

_SCORE_TABLE_HEADER_RE = re.compile(r"^\s*\|\s*Score\s*\|", re.IGNORECASE)
_SCORE_ROW_RE = re.compile(r"^\s*\|\s*`([a-z][a-z0-9_]*)`\s*\|")


def _collect_score_names_from_code() -> set[str]:
    tree = ast.parse(SCORING_PY.read_text(encoding="utf-8"))
    names: set[str] = set()

    for node in ast.walk(tree):
        # Capture name="..." kwargs on score(...) / lf.create_score(...) calls.
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg != "name":
                    continue
                value = kw.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    names.add(value.value)
        # Capture keys of the always-written ``scores = {...}`` dict literal
        # inside write_langfuse_scores plus any later ``scores["..."] = ...``
        # subscript assignments (e.g. results_count, no_results).
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
                if (
                    isinstance(target, ast.Subscript)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "scores"
                    and isinstance(target.slice, ast.Constant)
                    and isinstance(target.slice.value, str)
                ):
                    names.add(target.slice.value)

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
    code_names = _collect_score_names_from_code() - DOC_EXEMPT_SCORE_NAMES
    doc_names = _collect_score_names_from_doc()
    missing = sorted(code_names - doc_names)
    assert not missing, (
        "#1956: docs/RAG_QUALITY_SCORES.md is missing rows for scores emitted by "
        "src/scoring.py. Add a row per name with type and description, "
        "or add an entry to DOC_EXEMPT_SCORE_NAMES with a reason. Missing names: "
        f"{missing}"
    )


def test_every_documented_score_is_emitted_by_code() -> None:
    code_names = _collect_score_names_from_code()
    doc_names = _collect_score_names_from_doc()
    stale = sorted(doc_names - code_names)
    assert not stale, (
        "#1956: docs/RAG_QUALITY_SCORES.md lists scores that are not emitted by "
        "src/scoring.py. Remove the stale rows or restore the missing "
        f"score writes. Stale names: {stale}"
    )


def test_main_query_score_count_is_above_legacy_14() -> None:
    code_names = _collect_score_names_from_code()
    # Legacy SDK registry claimed "14 RAG scores"; the live emitter is far
    # broader (latency breakdown, voice path, injection defense, memory,
    # checkpointer, sources, nurturing). Pin a floor so the legacy number
    # cannot creep back in silently.
    assert len(code_names) > 30, (
        f"Expected scoring.py to emit more than 30 distinct score names, found {len(code_names)}: "
        f"{sorted(code_names)}"
    )
