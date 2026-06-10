# DEPS-15 dead-code cleanup audit

This audit verifies candidate symbols with repository-wide `rg` reference checks
before removal. Mini App candidates remain blocked by #2430. Langfuse/OTel
helpers that still have active imports or tests remain in place until #2434 and
#2435 land.

Removed in this slice:

| Symbol | File | Verification result |
|---|---|---|
| `find_merged_branches` | `scripts/archive/git_hygiene.py` | Only the definition existed. |
| `find_no_upstream_branches` | `scripts/archive/git_hygiene.py` | Only the definition existed. |
| `find_stale_worktrees` | `scripts/archive/git_hygiene.py` | Only the definition existed. |
| `fix_merged_branches` | `scripts/archive/git_hygiene.py` | Only the compatibility shim existed. |
| `_resolve` | `src/observability_sentry.py` | Only the private definition existed; resolver-specific helpers remain used. |
| `embed_queries_sync` | `src/models/contextualized_embedding.py` | Only the sync-wrapper definition existed. |

Kept after verification:

- `rag_task` is used by `scripts/run_experiment.py` when creating the dataset
  run task.
- `traced_pipeline`, `is_endpoint_reachable`, and `disable_otel_exporter` still
  have active imports/tests.
- `reset_pipeline_factory_cache` and `mark_processing_sync` are covered by unit
  tests and remain public test/reset helpers.
- Docling `chunk_document`, `convert_file`, and `health_check` remain part of
  the ingestion compatibility/export surface.
