# Scripts Inventory — 2026-05

Working artefact for [#1997](https://github.com/yastman/rag/issues/1997)
("scripts: classify stale manual scripts into keep / archive / delete").
Sub-issue of the [#1978](https://github.com/yastman/rag/issues/1978)
dead-code audit. Companion to:

- [`dead-code-audit-2026-05.md`](dead-code-audit-2026-05.md) — broader
  inventory of removed runtime modules.
- [`script-native-migration-matrix.md`](script-native-migration-matrix.md)
  — per-script SDK / native migration tracking.
- [`scripts/README.md`](../../scripts/README.md) — operator-facing
  manual-script index.

## Methodology

Each `scripts/*.py` was checked for:

1. **Makefile target** — `grep -n 'scripts/<name>'` over `Makefile`.
2. **CI workflow** — `grep -rn 'scripts/<name>'` over `.github/workflows/`.
3. **Doc reference** — `grep -rn 'scripts/<name>'` over `docs/` and the
   per-area `README.md` files.
4. **Python import** — `grep -rn 'from scripts.<name>'` over `src/`,
   `telegram_bot/`, `tests/`.
5. **Hardcoded fixture paths** — does the script reference a collection
   name, host, or env that no longer exists?

A script enters `delete_now` only when **(1) and (2) and (3) and (4)**
return zero. `archive` is reserved for scripts with no current callers
but documented historical value. `migrate` is reserved for scripts that
should move into a Makefile target, the test suite, or a runbook.

## Inventory (42 scripts)

### `keep` — referenced by Makefile, CI, tests, or documented runbook

These scripts have at least one verified caller. Owner column lists the
most likely subject-matter owner derived from the call site, not a
formal CODEOWNERS assignment.

| Script | Caller(s) | Owner |
|--------|-----------|-------|
| `check_image_drift.py` | `Makefile` (image-drift, image-drift-fix) | infra |
| `check_markdown_links.py` | `Makefile` (docs-check) | docs |
| `check_test_tracking.py` | `tests/unit/scripts/test_check_test_tracking.py` (5 tests) | testing |
| `check_unique_test_names.py` | `tests/contract/test_no_new_duplicate_test_names.py` + #1539 ratchet | testing |
| `e2e/runner.py` | `Makefile` (test-e2e family, ~6 targets) | e2e |
| `e2e/langfuse_latest_trace_audit.py` | `Makefile` (test-e2e-trace-audit) | e2e |
| `eval/goldset_sync.py` | `Makefile` (eval-goldset-sync) | eval |
| `eval/run_experiment.py` | `Makefile` (eval-run) | eval |
| `generate_gold_set.py` | `Makefile` (gold-set, gold-set-dry-run) | eval |
| `generate_test_properties.py` | `Makefile` (apartments-generate) | apartments |
| `index_test_properties.py` | `Makefile` (apartments-index) | apartments |
| `issue_queue_audit.py` | `Makefile` (issue-queue-audit) | governance |
| `pr_queue_audit.py` | `Makefile` (pr-queue-audit) | governance |
| `qdrant_snapshot.py` | `Makefile` (qdrant-snapshot) | infra |
| `run_experiment.py` | `Makefile` (eval-run, eval-run-named) | eval |
| `run_legal_grounding_audit.py` | `scripts/README.md` (Validation table) | retrieval/eval |
| `setup_ingestion_collection.py` | `Makefile` (qdrant-ensure) | ingestion |
| `validate_done_json.py` | `.pre-commit-config.yaml` (DONE JSON schema check) | governance |
| `validate_queries.py` | imported by `scripts/validate_traces.py` + 14 tests | observability |
| `validate_traces.py` | `Makefile` (validate-traces, validate-traces-fast) | observability |
| `validate_trace_runtime.py` | `Makefile` (validate-trace-runtime) | observability |
| `validate_voice_traces.py` | `Makefile` (validate-voice-traces) | observability |

### `keep` — operationally important manual tools

Scripts the issue body explicitly cautions against deleting (prod / VPS /
CRM / scoring side effects). They have no Makefile/CI hook by design —
they are operator-run on demand. Each row records the documented
owner / use case so a future audit does not flag them as dead.

| Script | Use case | Owner |
|--------|----------|-------|
| `kommo_seed.py` | One-shot CRM bootstrap (create funnels, custom fields). Touches live Kommo CRM. | crm |
| `langfuse_alert.py` / `langfuse_triage.py` | Operator-run trace triage & alerting helpers. | observability |
| `qdrant_ensure_indexes.py` | Operator-run safety: ensure payload indexes exist on a target collection. | retrieval |
| `setup_langfuse_dashboards.py` | Operator-run Langfuse dashboard provisioning. | observability |
| `setup_score_configs.py` | Operator-run Langfuse score config bootstrap. | observability |
| `update_advisor_prompts.py` | Operator-run Langfuse prompt sync for the AI advisor. | observability |
| `index_contextual.py` / `index_contextual_api.py` / `index_local_docs.py` / `index_services.py` | Operator-run ingest helpers for legacy collections. | ingestion |
| `setup_qdrant_collection.py` / `setup_binary_collection.py` / `setup_scalar_collection.py` | Operator-run Qdrant collection bootstrap variants. | infra |
| `export_traces_to_dataset.py` | Operator-run Langfuse → eval dataset export. | eval |

### `delete_now` — proven dead, deleted in this slice

| Script | Evidence |
|--------|----------|
| `test_search_quality.py` | (1) zero Makefile / CI / docs / Python-import refs; (2) hard-codes a Qdrant collection (`contextual_bulgaria`, no `_voyage` suffix) that does not appear anywhere in `src/`, `telegram_bot/`, or `.env.example` — the production collection name has long moved on; (3) a one-off "search quality after `m=0` optimization" smoke against `localhost:6333` and `localhost:8000` BGE-M3 with five hard-coded queries. The `m=0` HNSW tweak is historical. Pinned by `tests/contract/test_dead_code_audit_2026_05_contract.py`. |

### `archive` — deferred (no live caller, but historical / reproducibility value)

| Script | Why deferred |
|--------|--------------|
| `benchmark_acorn.py` | ACORN filtered-search microbenchmark. The retrieval module that consumes it (`src/retrieval/search_engines.py`) is itself classified as `needs_decision` in `dead-code-audit-2026-05.md` (referenced only by a `telegram_bot/services/qdrant.py` comment). Hold this script until that decision is made; otherwise we lose the benchmark fixture for the ACORN feature. |
| `benchmark_llm.py` | LiteLLM-vs-Cerebras-direct latency benchmark. No callers, but useful for future model-pricing decisions; archive instead of delete so the methodology is recoverable. |
| `test_int8_vs_binary.py` / `test_quantization_ab.py` / `test_contextualized_ab.py` | A/B benchmarking scripts; their results are historical baselines for the binary-quantization decision. No active callers, but the methodology is the artefact. |
| `reindex_to_binary.py` | One-time migration helper for the binary-quantization rollout. Keep for disaster-recovery rebuild scenarios; document owner = infra. |
| `index_test_data.py` | One-off seed for a test collection; not in any Makefile target today. |

`archive` rows are intentionally **not deleted** in this slice. A
follow-up issue may move them to a `scripts/archive/` directory or wrap
them under a Makefile target so they regain a documented caller.

### `migrate` — deferred (works today but should move)

(none in this audit — re-evaluate after `archive` rows are resolved)

### `needs_decision` — explicitly deferred

| Script | Question |
|--------|----------|
| (carried over from `dead-code-audit-2026-05.md`) | The `src/retrieval/search_engines.py` ACORN feature decision affects whether `benchmark_acorn.py` is `archive` or `delete_now`. |

## Acceptance against #1997

- [x] Inventory built with `keep` / `archive` / `delete_now` /
      `migrate` / `needs_decision` sections.
- [x] Owner / reason recorded for every kept manual script.
- [x] At least one confirmed-dead deletion landed in this PR
      (`scripts/test_search_quality.py`).
- [ ] Subsequent slices fold `archive` rows into a `scripts/archive/`
      directory or remove them once the dependent decisions land.

## Refs

- [#1997](https://github.com/yastman/rag/issues/1997) (this issue).
- Parent: [#1978](https://github.com/yastman/rag/issues/1978).
- Companion docs: [`dead-code-audit-2026-05.md`](dead-code-audit-2026-05.md),
  [`scripts/README.md`](../../scripts/README.md),
  [`script-native-migration-matrix.md`](script-native-migration-matrix.md).
- Contract test: [`tests/contract/test_dead_code_audit_2026_05_contract.py`](../../tests/contract/test_dead_code_audit_2026_05_contract.py)
  (extend with the deletion pinned by this PR).
