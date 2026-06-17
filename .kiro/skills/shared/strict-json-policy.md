# Shared: Markdown-first / strict-JSON policy

> Single source of truth for the report-contract mode. Referenced by the swarm
> phase skills instead of being restated in each (#2305 P2/P3).

## Default: Markdown-first

- Workers write compact **Markdown** reports.
- Acceptance is **human-like orchestrator reasoning** over the report.
- Rails (`accept_worker_report.py`, `launch_kiro_worker.sh`) perform **mechanical
  checks only** and emit facts, never a verdict. `schema-valid != accepted`.

## Legacy strict JSON (opt-in)

Strict JSON artifacts, signal validators, registry state, and wake-up receipts
are **legacy strict mode**. Use them only when one of these holds:

- the terminal artifact path already ends in `.json`, or
- the user explicitly sets `SWARM_CONTRACT=strict_json`
  (`SWARM_ALLOW_STRICT_JSON=1`), or
- an automated launch must consume the result without orchestrator
  interpretation.

The JSON validators (`scripts/validate_done_json.py`,
`scripts/validate_worker_signal.py`) are gated behind `KIRO_STRICT_REPORT=1`
and are a no-op otherwise.

Do not request strict JSON for normal Markdown intake / acceptance.
