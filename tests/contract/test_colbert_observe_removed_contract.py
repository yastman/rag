"""Deprecated ColBERT reranker must not carry @observe (#2214).

`ColbertRerankerService` is deprecated — server-side ColBERT via
`hybrid_search_rrf_colbert()` (#569) is the production path, emitting the
`qdrant-hybrid-search-rrf-colbert` span. If the client-side service keeps an
`@observe(name="colbert-rerank")` and is ever re-enabled, it double-emits a
second reranking span. This contract locks the decorator out and keeps the
deprecated module from re-introducing the span catalog entry.

It also documents the rule that `colbert-rerank` is intentionally absent from
the `trace_contract.yaml` span catalog (removed alongside the decorator).
"""

from __future__ import annotations

import ast
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
COLBERT_MODULE = REPO_ROOT / "telegram_bot" / "services" / "colbert_reranker.py"
TRACE_CONTRACT = REPO_ROOT / "tests" / "observability" / "trace_contract.yaml"


def _observe_calls(source: str) -> list[str]:
    """Return @observe(name=...) names found in the module (decorator or call)."""
    tree = ast.parse(source)
    names: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_observe = (isinstance(func, ast.Attribute) and func.attr == "observe") or (
            isinstance(func, ast.Name) and func.id == "observe"
        )
        if not is_observe:
            continue
        name_found: str | None = None
        for kw in node.keywords:
            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                name_found = kw.value.value
        names.append(name_found if name_found is not None else "<observe>")
    return names


def _imports_observe(source: str) -> bool:
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and any(a.name == "observe" for a in node.names):
            return True
    return False


def _all_catalog_spans(contract: dict) -> set[str]:
    spans: set[str] = set(contract.get("required_families", []))
    for group in (contract.get("spans") or {}).values():
        if isinstance(group, list):
            spans.update(group)
    return spans


class TestColbertObserveRemoved:
    def test_module_exists(self) -> None:
        assert COLBERT_MODULE.exists(), f"missing: {COLBERT_MODULE}"

    def test_no_observe_decorator_in_deprecated_module(self) -> None:
        source = COLBERT_MODULE.read_text(encoding="utf-8")
        found = _observe_calls(source)
        assert not found, (
            "Deprecated ColbertRerankerService must not carry @observe (#2214): "
            f"found {found}. Server-side ColBERT (qdrant-hybrid-search-rrf-colbert) "
            "is the production span; a client-side colbert-rerank span double-emits."
        )

    def test_module_does_not_import_observe(self) -> None:
        source = COLBERT_MODULE.read_text(encoding="utf-8")
        assert not _imports_observe(source), (
            "colbert_reranker.py should not import `observe` once the decorator is removed."
        )

    def test_colbert_rerank_absent_from_span_catalog(self) -> None:
        contract = yaml.safe_load(TRACE_CONTRACT.read_text(encoding="utf-8"))
        spans = _all_catalog_spans(contract)
        assert "colbert-rerank" not in spans, (
            "'colbert-rerank' must be removed from trace_contract.yaml when the "
            "deprecated @observe is stripped, or the trace-families contract "
            "(all_contract_spans_exist_in_codebase) will fail."
        )


class TestDetectorSelfChecks:
    def test_detects_observe_decorator(self) -> None:
        src = "from telegram_bot.observability import observe\n@observe(name='x')\ndef f():\n    pass\n"
        assert _observe_calls(src) == ["x"]
        assert _imports_observe(src)

    def test_clean_module_has_none(self) -> None:
        src = "def f():\n    return 1\n"
        assert _observe_calls(src) == []
        assert not _imports_observe(src)
