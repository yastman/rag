"""Mini App browser-tracing decision contract (#2273).

Locks in the research-only decision recorded in
``docs/observability/MINIAPP_BROWSER_TRACING_DECISION.md`` so it cannot silently
disappear or drift from the code it describes:

* a clear scope decision must be stated (in-scope / deferred / out-of-scope);
* the doc must keep pointing at the candidate SDK-native browser path
  (OpenTelemetry JS web), not a non-existent Langfuse browser tracer;
* the doc's central claim — that ``mini_app/api.py`` extraction stays
  SDK-native via FastAPI auto-instrumentation — must remain true in code, so
  the "no backend change needed" decision is not built on a stale fact.

This mirrors ``test_voice_tracing_baseline_contract.py`` (#2257): a documented
decision, enforced.
"""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DECISION_DOC = REPO_ROOT / "docs" / "observability" / "MINIAPP_BROWSER_TRACING_DECISION.md"
MINIAPP_API = REPO_ROOT / "mini_app" / "api.py"


def _doc_text() -> str:
    return DECISION_DOC.read_text(encoding="utf-8")


def test_decision_doc_exists() -> None:
    assert DECISION_DOC.exists(), f"missing decision record: {DECISION_DOC}"


def test_doc_states_a_clear_scope_decision() -> None:
    lowered = _doc_text().lower()
    assert any(marker in lowered for marker in ("out of scope", "deferred", "in scope")), (
        "docs/observability/MINIAPP_BROWSER_TRACING_DECISION.md must state a clear "
        "browser-tracing scope decision: in-scope, deferred, or out-of-scope (#2273)."
    )


def test_doc_references_sdk_native_browser_path() -> None:
    """The candidate path must be OpenTelemetry JS web, not a Langfuse browser SDK."""
    text = _doc_text()
    for token in ("@opentelemetry/sdk-trace-web", "@opentelemetry/instrumentation-fetch"):
        assert token in text, (
            "The decision record must document the OpenTelemetry JS web path "
            f"({token}) as the SDK-native browser option (#2273)."
        )
    assert "traceparent" in text.lower(), (
        "The decision record must discuss W3C traceparent propagation (#2273)."
    )


def test_backend_extraction_claim_matches_code() -> None:
    """The doc claims mini_app/api.py extracts trace context SDK-natively.

    Keep that claim honest: mini_app/api.py must actually wire FastAPI
    auto-instrumentation (which extracts traceparent/baggage). If this ever
    changes, the "no backend change needed" rationale must be revisited.
    """
    doc = _doc_text()
    assert "instrument_fastapi_app" in doc, (
        "The decision rationale relies on FastAPI auto-extraction; the doc must "
        "name instrument_fastapi_app (#2273)."
    )
    api_src = MINIAPP_API.read_text(encoding="utf-8")
    assert "instrument_fastapi_app(app)" in api_src, (
        "mini_app/api.py no longer calls instrument_fastapi_app(app); the #2273 "
        "decision assumed SDK-native backend traceparent extraction — revisit the "
        "decision record."
    )
