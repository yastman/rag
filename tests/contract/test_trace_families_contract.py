"""Trace families contract tests.

Verifies that the canonical trace_contract.yaml is consistent with the codebase:
  - required trace families have @observe decorators
  - all contract spans exist in production code
  - no undocumented @observe spans exist outside evaluation
  - score keys are non-empty and match the scoring module
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml


CONTRACT_PATH = Path(__file__).resolve().parent.parent / "observability" / "trace_contract.yaml"

# Directories to scan for @observe decorators (production code only)
_SCAN_DIRS = [
    Path(__file__).resolve().parent.parent.parent / "telegram_bot",
    Path(__file__).resolve().parent.parent.parent / "src",
]
# Exclude non-production code from the undocumented-spans check
_EXCLUDE_PATTERNS = ["src/evaluation", ".venv/"]

# 13 core RAG scores from tests/unit/observability/test_trace_contracts.py::_CORE_RAG_SCORES
# (hyde_used removed in #754 — was a stub, HyDE not implemented)
_CORE_RAG_SCORES = [
    "query_type",
    "latency_total_ms",
    "semantic_cache_hit",
    "embeddings_cache_hit",
    "search_cache_hit",
    "rerank_applied",
    "rerank_cache_hit",
    "results_count",
    "no_results",
    "llm_used",
    "confidence_score",
    "llm_ttft_ms",
    "llm_response_duration_ms",
]


def collect_observe_names(
    directories: list[Path],
    exclude_patterns: list[str] | None = None,
) -> set[str]:
    """AST-scan directories and return all @observe(name=...) values."""
    names: set[str] = set()
    always_exclude = [".venv/"]
    exclude_patterns = (exclude_patterns or []) + always_exclude
    for directory in directories:
        if not directory.exists():
            continue
        for py_file in directory.rglob("*.py"):
            if any(pat in str(py_file) for pat in exclude_patterns):
                continue
            try:
                tree = ast.parse(py_file.read_text())
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                is_observe = (isinstance(func, ast.Attribute) and func.attr == "observe") or (
                    isinstance(func, ast.Name) and func.id == "observe"
                )
                if not is_observe:
                    continue
                for kw in node.keywords:
                    if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                        names.add(kw.value.value)
    return names


# ---------------------------------------------------------------------------
# a) Contract YAML exists and is parseable
# ---------------------------------------------------------------------------


def test_contract_yaml_exists():
    assert CONTRACT_PATH.exists(), f"trace_contract.yaml not found at {CONTRACT_PATH}"
    data = yaml.safe_load(CONTRACT_PATH.read_text())
    assert isinstance(data, dict)
    assert "required_families" in data
    assert "spans" in data
    assert "scores" in data


# ---------------------------------------------------------------------------
# b) required_families is non-empty
# ---------------------------------------------------------------------------


def test_required_families_non_empty(required_families):
    assert required_families, "required_families must not be empty"
    assert len(required_families) >= 1


# ---------------------------------------------------------------------------
# c) All required families have a matching @observe(name=...) decorator
# ---------------------------------------------------------------------------


def test_all_required_families_have_observe_decorator(required_families):
    code_spans = collect_observe_names(_SCAN_DIRS)
    missing = [fam for fam in required_families if fam not in code_spans]
    assert not missing, (
        "Required trace families missing @observe decorator in telegram_bot/ or src/:\n"
        + "\n".join(f"  - {m}" for m in sorted(missing))
    )


# ---------------------------------------------------------------------------
# d) All contract spans exist somewhere in the codebase
# ---------------------------------------------------------------------------


def test_all_contract_spans_exist_in_codebase(all_contract_spans):
    code_spans = collect_observe_names(_SCAN_DIRS)
    missing = [span for span in all_contract_spans if span not in code_spans]
    assert not missing, (
        "Contract spans not found by @observe AST scan in telegram_bot/ or src/:\n"
        + "\n".join(f"  - {m}" for m in sorted(missing))
    )


# ---------------------------------------------------------------------------
# e) No undocumented @observe spans (reverse check)
# ---------------------------------------------------------------------------


def test_no_undocumented_observe_spans(all_contract_spans, required_families):
    code_spans = collect_observe_names(_SCAN_DIRS, exclude_patterns=_EXCLUDE_PATTERNS)
    # Contract covers both the spans section and the required_families entries
    documented = set(all_contract_spans) | set(required_families)
    undocumented = code_spans - documented
    assert not undocumented, (
        "Found @observe spans in production code not listed in trace_contract.yaml.\n"
        "Add them to an appropriate group in the 'spans' section:\n"
        + "\n".join(f"  - {s}" for s in sorted(undocumented))
    )


# ---------------------------------------------------------------------------
# f) Score keys are non-empty
# ---------------------------------------------------------------------------


def test_score_keys_non_empty(score_keys):
    assert score_keys, "score_keys must not be empty"
    assert len(score_keys) >= 1


# ---------------------------------------------------------------------------
# g) core_rag scores in contract match the scoring module constant
# ---------------------------------------------------------------------------


def test_core_rag_scores_match_scoring_module(trace_contract):
    contract_core_rag = trace_contract["scores"]["core_rag"]
    assert sorted(contract_core_rag) == sorted(_CORE_RAG_SCORES), (
        "contract.scores.core_rag does not match _CORE_RAG_SCORES from test_trace_contracts.py.\n"
        f"Contract: {sorted(contract_core_rag)}\n"
        f"Expected: {sorted(_CORE_RAG_SCORES)}"
    )
