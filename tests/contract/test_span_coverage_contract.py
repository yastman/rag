"""Span coverage contract tests (AST-based, no Docker needed).

Verifies that sensitive spans disable auto-capture and light spans use auto-capture.
"""

import ast
from pathlib import Path

import pytest


# Root of the repo (two levels up from this file)
REPO_ROOT = Path(__file__).parent.parent.parent

SCAN_DIRS = [
    REPO_ROOT / "telegram_bot",
    REPO_ROOT / "src",
]
EXCLUDE_DIRS = ["tests/", "src/evaluation/", ".venv/"]

# Spans that carry large/sensitive payloads — must have capture_input=False, capture_output=False
SENSITIVE_SPANS = [
    # Graph nodes (heavy)
    "node-cache-check",
    "node-cache-store",
    "node-retrieve",
    "node-generate",
    "node-respond",
    "node-summarize",
    "transcribe",
    # Agent pipeline
    "rag-pipeline",
    "cache-check",
    "hybrid-retrieve",
    "retrieval.initial",
    "retrieval.relax",
    "cache-store",
    # Agent tools
    "tool-rag-search",
    "tool-history-search",
    "tool-apartment-search",
    # History graph
    "history-retrieve",
    "history-summarize",
    # Pipeline
    "detect-agent-intent",
    "client-direct-pipeline",
    # Classify
    "classify-query",
    # Cache (all 12)
    "cache-semantic-check",
    "cache-semantic-store",
    "cache-exact-get",
    "cache-exact-store",
    "cache-embedding-get",
    "cache-embedding-store",
    "cache-sparse-get",
    "cache-sparse-store",
    "cache-search-get",
    "cache-search-store",
    "cache-rerank-get",
    "cache-rerank-store",
    # BGE-M3 client (all 5)
    "bge-m3-encode-dense",
    "bge-m3-encode-sparse",
    "bge-m3-encode-hybrid",
    "bge-m3-rerank",
    "bge-m3-encode-colbert",
    # Qdrant (all 8)
    "qdrant-ensure-collection",
    "qdrant-apply-strict-mode",
    "qdrant-ensure-alias",
    "qdrant-hybrid-search-rrf",
    "qdrant-hybrid-search-rrf-colbert",
    "qdrant-batch-search-rrf",
    "qdrant-search-score-boosting",
    "qdrant-mmr-rerank",
    # History service (all 4)
    "history-save",
    "history-search",
    "history-delete",
    "history-get-session-turns",
    # Services
    "service-generate-response",
    "detect-response-style",
    "get-prompt",
    "kommo-token-refresh",
    "apartments-hybrid-search",
    "apartments-scroll",
    "apartment-filter-parse",
    "apartment-extraction-pipeline",
    "apartment-llm-extract",
    "advisor-llm-call",
    "session-summary-generate",
    "nurturing-llm-generate",
    # Bot command/menu/callback flows
    "cmd-start",
    "cmd-clear",
    "cmd-clearcache",
    "cmd-call",
    "menu-router",
    "menu-search",
    "menu-services",
    "menu-viewing",
    "menu-bookmarks",
    "menu-ask",
    "menu-manager",
    "cb-ask",
    "cb-service",
    "cb-cta",
    "cb-favorite",
    "cb-results",
    "cb-card",
    "cb-feedback",
    "cb-feedback-reason",
    "cb-clearcache",
    # Dialog/handler spans with capture disabled
    "dialog-crm-create-note",
    "dialog-crm-create-contact",
    "dialog-funnel-search",
    "dialog-crm-create-task",
    "dialog-crm-create-lead",
    "phone-lead-capture",
    "demo-search",
    "crm-quick-complete",
    "crm-quick-note",
    # Entry points
    "voice-session",
    "rag-api-query",
    # Ingestion (all 6)
    "ingestion-cli-run",
    "ingestion-cli-preflight",
    "ingestion-flow-run-once",
    "ingestion-flow-watch",
    "ingestion-qdrant-delete-file",
    "ingestion-qdrant-upsert-chunks",
]

# Light spans — use auto-capture (capture_input should NOT be explicitly set to False)
LIGHT_SPANS = [
    "node-classify",
    "node-grade",
    "node-rerank",
    "node-rewrite",
    "node-guard",
    "crm-get-deal",
    "crm-create-lead",
    "crm-update-lead",
    "tool-mortgage-calculator",
    "tool-daily-summary",
    "tool-handoff",
    "history-guard",
    "history-grade",
    "history-rewrite",
    "grade-documents",
    "rerank",
    "query-rewrite",
    "colbert-rerank",
]


def collect_observe_decorators(
    directories: list[Path],
    exclude_dirs: list[str] | None = None,
) -> dict[str, dict]:
    """Return dict: span_name -> {capture_input, capture_output, file, line}."""
    results: dict[str, dict] = {}
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
                is_observe = (isinstance(func, ast.Attribute) and func.attr == "observe") or (
                    isinstance(func, ast.Name) and func.id == "observe"
                )
                if not is_observe:
                    continue
                kwargs = {kw.arg: kw.value for kw in node.keywords}
                name_node = kwargs.get("name")
                if not isinstance(name_node, ast.Constant):
                    continue
                span_name = name_node.value
                ci = kwargs.get("capture_input")
                co = kwargs.get("capture_output")
                results[span_name] = {
                    "capture_input": getattr(ci, "value", None) if ci else None,
                    "capture_output": getattr(co, "value", None) if co else None,
                    "file": str(py_file),
                    "line": node.lineno,
                }
    return results


@pytest.fixture(scope="session")
def observed_spans() -> dict[str, dict]:
    return collect_observe_decorators(SCAN_DIRS, EXCLUDE_DIRS)


@pytest.mark.parametrize("span_name", SENSITIVE_SPANS)
def test_sensitive_spans_have_capture_disabled(
    observed_spans: dict[str, dict], span_name: str
) -> None:
    """Sensitive spans must disable auto-capture to avoid leaking large payloads."""
    assert span_name in observed_spans, (
        f"Span '{span_name}' not found in codebase. "
        f"Add @observe(name='{span_name}', capture_input=False, capture_output=False) "
        f"or remove it from SENSITIVE_SPANS."
    )
    info = observed_spans[span_name]
    assert info["capture_input"] is False, (
        f"Span '{span_name}' at {info['file']}:{info['line']} "
        f"must have capture_input=False (got {info['capture_input']!r})"
    )
    assert info["capture_output"] is False, (
        f"Span '{span_name}' at {info['file']}:{info['line']} "
        f"must have capture_output=False (got {info['capture_output']!r})"
    )


def test_required_retrieval_stage_spans_present(observed_spans: dict[str, dict]) -> None:
    assert "retrieval.initial" in observed_spans
    assert "retrieval.relax" in observed_spans


@pytest.mark.parametrize("span_name", LIGHT_SPANS)
def test_light_spans_have_default_capture(observed_spans: dict[str, dict], span_name: str) -> None:
    """Light spans should use auto-capture (capture_input not explicitly set to False)."""
    if span_name not in observed_spans:
        pytest.skip(f"Span '{span_name}' not found in codebase — skip drift check")
    info = observed_spans[span_name]
    assert info["capture_input"] is not False, (
        f"Light span '{span_name}' at {info['file']}:{info['line']} "
        f"should NOT have capture_input=False. Remove the flag or move to SENSITIVE_SPANS."
    )


def test_all_observed_spans_accounted_for(observed_spans: dict[str, dict]) -> None:
    """Drift detection: any span with capture_input=False must be in SENSITIVE_SPANS.

    If a developer adds a new @observe(capture_input=False, ...) but forgets to
    add it to SENSITIVE_SPANS, this test will catch the drift.
    """
    sensitive_set = set(SENSITIVE_SPANS)
    unaccounted = []
    for span_name, info in observed_spans.items():
        if info["capture_input"] is False and span_name not in sensitive_set:
            unaccounted.append(f"  '{span_name}' at {info['file']}:{info['line']}")
    assert not unaccounted, (
        "The following spans have capture_input=False but are not in SENSITIVE_SPANS.\n"
        "Add them to SENSITIVE_SPANS in tests/contract/test_span_coverage_contract.py:\n"
        + "\n".join(unaccounted)
    )


def test_sensitive_spans_match_yaml_contract(sensitive_spans: list[str]) -> None:
    """Ensure SENSITIVE_SPANS constant matches trace_contract.yaml sensitive_spans.

    Catches drift between the hardcoded test list and the canonical YAML contract.
    """
    python_set = set(SENSITIVE_SPANS)
    yaml_set = set(sensitive_spans)
    only_python = python_set - yaml_set
    only_yaml = yaml_set - python_set
    assert python_set == yaml_set, (
        f"SENSITIVE_SPANS drift between test and YAML contract.\n"
        f"Only in Python constant: {sorted(only_python)}\n"
        f"Only in YAML contract: {sorted(only_yaml)}"
    )
