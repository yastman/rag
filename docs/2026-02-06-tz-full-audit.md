# Full Audit: ТЗ `2026-02-01-rag-2026-tz.md`

Date: 2026-02-06
Project root: `/opt/rag-fresh`
Primary spec: `docs/plans/2026-02-01-rag-2026-tz.md`

## Scope

- Full cross-check of declared milestone status vs:
  - code (`src/`, `telegram_bot/`)
  - automation (`Makefile`, CI workflow)
  - Docker/runtime state (`vps-*` containers)
  - official docs references (Context7 for `qdrant-client`, `uv`)

## Executive Summary

- Product is strongly `production-like` (stable stack, healthy containers, key features implemented).
- Main remaining risks are **status integrity of the plan** and **operational preflight UX**.
- Several milestones marked `✅ COMPLETE` still contain unresolved or conflicting sub-items.

## Findings (ordered by severity)

| ID | Severity | Domain | Finding | Evidence | Recommendation |
|---|---|---|---|---|---|
| TZ-01 | Critical | Ops preflight | `make test-bot-health` is not usable on current VPS runtime from host (defaults to localhost, no published Qdrant port) | `Makefile:270`, `scripts/test_bot_health.sh:4`, runtime: `make test-bot-health ...` -> `Qdrant is unreachable at http://localhost:6333` | Add VPS-safe mode (e.g., `docker exec vps-bot` helper target or host-published health endpoint profile) |
| TZ-02 | High | Plan integrity | Milestone A is marked `✅ COMPLETE`, but has unresolved items (including missing `retrieval_profile`) | `docs/plans/2026-02-01-rag-2026-tz.md:566`, open items: `:570`, `:571`, `:579` | Split `COMPLETE` into `COMPLETE (except pre-existing)` or move unresolved items into explicit follow-up milestone |
| TZ-03 | High | Plan integrity | Milestone K is marked `✅ COMPLETE`, but same section still contains large unresolved checklist template (76 open items) | `docs/plans/2026-02-01-rag-2026-tz.md:871`, open items start `:900` onward | Keep only executed acceptance checklist in completed milestone; move backlog template to separate `K-next` section |
| TZ-04 | High | Ingestion path consistency | Legacy CocoIndex GDrive path is still callable in code and explicitly returns not implemented, while Milestone J is complete via different architecture | `src/ingestion/service.py:210`, `src/ingestion/service.py:214`; `docs/plans/2026-02-01-rag-2026-tz.md:802` | Keep legacy path but hard-label as deprecated in code/docs and route all operator docs to `ingest-gdrive-run/watch` flow |
| TZ-05 | Medium | Plan consistency | Early plan context still contains stale diagnostics/tasks now superseded by completed milestones | unchecked legacy tasks: `docs/plans/2026-02-01-rag-2026-tz.md:73-75`; stale narrative around old state: `:44` | Add "historical snapshot" label for section `0.0.x` or archive outdated troubleshooting block |
| TZ-06 | Medium | Feature contract | `retrieval_profile` contract remains absent in central settings while documented as target profile mechanism | contract in plan: `docs/plans/2026-02-01-rag-2026-tz.md:530`; partially acknowledged unresolved: `:579`; settings lacks field (`src/config/settings.py`) | Implement `retrieval_profile` with mapping (`fast/balanced/quality`) or remove contract from "implemented" scope |
| TZ-07 | Medium | Tooling policy | `uv-first` is mostly done, but claim "removed direct pip from docs/scripts/CI" is broader than reality across all docs corpus | claim: `docs/plans/2026-02-01-rag-2026-tz.md:917`; active CI already uv (`.github/workflows/ci.yml:17`, `:68`) but many historical docs still contain `pip install` | Narrow claim wording to "active CI + primary runbooks" or complete doc-wide migration |
| TZ-08 | Medium | Quantization rollout | Milestone B completed in code, but current VPS collection (`gdrive_documents_bge`) has no quantization config | runtime collection: `gdrive_documents_bge` -> `"quantization_config": null` via Qdrant API | Clarify B status as "implementation complete, not enabled in current VPS collection" |
| TZ-09 | Medium | Observability/noise | Ingestion logs remain very verbose at INFO (per-file/per-step spam) | runtime `docker logs vps-ingestion` shows high-frequency INFO lines from `qdrant_hybrid_target` | Move per-item logs to DEBUG, keep aggregated cycle summaries at INFO |
| TZ-10 | Low | Document status metadata | Header says "Ready for implementation" while many milestones are already completed | `docs/plans/2026-02-01-rag-2026-tz.md:4` | Update header to "In execution / Partially completed" |

## Verified as implemented

- Redis policy and samples aligned in VPS runtime: `volatile-lfu` + `maxmemory-samples=10`.
  - Runtime check: `docker exec vps-redis redis-cli CONFIG GET ...`
  - Config: `docker-compose.vps.yml:42`
- `test-redis` preflight is now environment-parameterized.
  - `REDIS_CONTAINER` and `EXPECTED_MAXMEMORY_SAMPLES`: `Makefile:12-13`
  - Target uses vars: `Makefile:236-263`
- ACORN support is available and integrated.
  - Code import path: `src/retrieval/search_engines.py:16`
  - Runtime check in venv: `models.AcornSearchParams` exists and works
- Root Dockerfile and CI are migrated to `uv` patterns.
  - `Dockerfile:1`, `Dockerfile:5`, cache mounts and `uv pip install`
  - CI uses `astral-sh/setup-uv` + `uv sync`: `.github/workflows/ci.yml:17`, `.github/workflows/ci.yml:68`
- Guardrails threshold drift fixed.
  - `telegram_bot/services/llm.py:17` (`LOW_CONFIDENCE_THRESHOLD = 0.3`)
  - Config wiring in bot init: `telegram_bot/bot.py:134`

## Context7 verification notes

1. Qdrant client (`/qdrant/qdrant-client`)
- Context7 snippets reliably showed filtered search patterns, but did not return direct `AcornSearchParams` examples.
- Therefore ACORN availability conclusion is based on runtime SDK introspection (`qdrant-client 1.16.2`) plus local code imports.

2. uv (`/astral-sh/uv`)
- Official docs confirm Docker best practices used here: multi-stage, cache mounts, `UV_LINK_MODE=copy`, `uv sync`/`uv pip`.

## Recommended next actions (priority)

1. Fix VPS preflight UX (`test-bot-health`) so operators can run health checks reliably from host.
2. Normalize milestone statuses (A/K/J) to eliminate `COMPLETE` vs unresolved-subitems ambiguity.
3. Decide and implement `retrieval_profile` contract (or remove from implementation scope).
4. Reduce ingestion INFO log noise to avoid signal loss in operations.
