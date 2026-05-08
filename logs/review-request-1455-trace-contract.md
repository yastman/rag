# Review Request: W-1455 Trace Contract

POLICY_ACK docs_lookup=forbidden local_only=true

## Scope Reviewed
- `scripts/validate_traces.py`
- `tests/unit/test_validate_traces_coverage_gate.py`
- `tests/contract/test_trace_families_contract.py`
- `docs/runbooks/LANGFUSE_TRACING_GAPS.md`

## Requirements Checklist
- [x] Coverage gate supports observation-level families under `telegram-message` root.
- [x] Root sanitized context contract enforced (`content_type`, `query_preview`, `query_hash`, `query_len`, `route`).
- [x] Raw Telegram objects are treated as contract violations.
- [x] Cache-hit path tolerated without forcing retrieve/generate spans.
- [x] Duplicate `detect-agent-intent` and WARNING observations are counted.
- [x] `litellm-acompletion` does not count as app coverage.
- [x] Existing non-Telegram direct families preserved (`rag-api-query`, `voice-session`, `ingestion-cli-run`).

## Diff Review Notes
- `check_required_trace_coverage()` now merges direct-family checks with nested observation checks from recent `telegram-message` traces.
- Added explicit contract telemetry fields in coverage output for debugging (`root_context_missing`, `root_context_pii_violations`, observation counters).
- Gate remains deterministic and backwards-compatible for direct-family-only callers via explicit empty overrides.
- Contract scan test now includes `services/` to match existing contract entries (`bge-m3-service-*`, `user-base-service-*`).

## Risk Review
- Main behavioral change: missing sanitized Telegram root context now fails `required_trace_families_present` via synthetic requirement `telegram-message-root-context`.
- No runtime behavior changes in bot/graph code; only validation/reporting contract.
- No secret/raw payloads added to logs or docs.

## Verification Evidence
- `uv run pytest tests/unit/test_validate_traces_coverage_gate.py -q`
- `uv run pytest tests/unit/test_validate_aggregates.py -q`
- `uv run pytest tests/contract/test_trace_families_contract.py tests/contract/test_span_coverage_contract.py -q`
- `make check`

## Review Decision
- **clean** (no unresolved blockers in scope)
