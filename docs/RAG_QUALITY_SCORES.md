# RAG quality scores

No quality scores are currently emitted. Langfuse-backed tracing and score writes were removed in #2844; restoring old score names without a live backend would create fake telemetry.

Active emitted score count: **0**

## Score inventory

| Score | Type | Description |
| --- | --- | --- |

The empty table is intentional. Add a row only when production code emits that exact score name.

## Current authority

[`src/observability/scores.py`](../src/observability/scores.py) is the canonical scoring module. Its `score`, `write_scores`, and `write_history_scores` functions are compatibility no-ops.

[`src/scoring.py`](../src/scoring.py) preserves the older import surface. Its `write_pipeline_scores` and `write_crm_scores` functions are also compatibility no-ops. [`telegram_bot/scoring.py`](../telegram_bot/scoring.py) only re-exports that surface.

Runtime calls may still pass through these compatibility functions, but they do not write scores. User feedback handling is separate from this retired per-query quality-score inventory.
