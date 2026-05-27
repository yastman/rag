# Runtime/operator docs refresh (#1193) — closeout

**Date:** 2026-05-27
**Issue:** [#1193 — docs: runtime and operator docs refresh (API, runbooks, pipeline, HITL)](https://github.com/yastman/rag/issues/1193)
**Status:** All superseded sub-issues are closed; canonical docs exist and were
last refreshed on 2026-05-26. Recommending close of #1193.

This note reconciles the runtime/operator docs epic against the documents that
ship on `dev` (commit `4ab8379`) on 2026-05-27. It is intentionally short — the
refresh work happened in earlier PRs that closed the listed sub-issues, and the
purpose of this doc is to document the discoverability surface so #1193 can be
closed cleanly.

## Definition of done — verification

> operator/runtime docs are grouped by actual use case rather than scattered
> one-off pages

`docs/indexes/` provides task-oriented entry points:

- `docs/indexes/fast-search.md` — by-request-type lookups (Langfuse traces, Qdrant, Redis, …)
- `docs/indexes/runtime-services.md` — Docker, ingestion, mini-app, bot, voice
- `docs/indexes/observability-and-storage.md` — Langfuse, Qdrant, Redis, LiteLLM, Postgres
- `docs/indexes/local-runtime.md` — local bot startup, Telegram E2E, Telethon sessions, polling locks
- `docs/indexes/engineering-workflows.md` — testing, triage, SDK lookup, dependency updates
- `docs/indexes/docker-sdk-map.md` — Compose ↔ SDK mapping

> API, pipeline, HITL, and troubleshooting docs are discoverable from a small
> set of canonical documents

| Concern | Canonical doc | Last refresh |
|---------|---------------|--------------|
| RAG API contract | `docs/RAG_API.md` (139 lines) | 2026-05-26 |
| API reference | `docs/API_REFERENCE.md` (157 lines) | 2026-05-26 |
| Pipeline routing | `docs/PIPELINE_ROUTING.md` (127 lines) | 2026-05-26 |
| Pipeline overview | `docs/PIPELINE_OVERVIEW.md` | 2026-05-26 |
| HITL flow | `docs/HITL.md` (139 lines), `docs/HITL_CRM_FLOW.md` (98 lines) | 2026-05-26 |
| Cache troubleshooting | `docs/TROUBLESHOOTING_CACHE.md` (187 lines), `docs/CACHE_DEGRADATION.md` (95 lines) | 2026-05-26 |
| Quality scores | `docs/RAG_QUALITY_SCORES.md` (122 lines) | 2026-05-26 |
| Runbook hub | `docs/runbooks/README.md` (76 lines) + 14 named runbooks | 2026-05-26 |

`docs/README.md` exposes all of the above through "Architecture & Design",
"Operations & Runbooks", and the "Task-Oriented Indexes" sections, so
operators land on the canonical surface from a single entry point.

> old fragmented issues above are closed as superseded by this epic

| Sub-issue | State |
|-----------|-------|
| #1096 — RAG API reference | CLOSED |
| #1098 — Critical-failure runbooks | CLOSED |
| #1102 — Pipeline-mode routing & dual-path architecture | CLOSED |
| #1104 — HITL flow for CRM | CLOSED |
| #1105 — Semantic cache troubleshooting | CLOSED |
| #1111 — 14 RAG quality scores | CLOSED |

## Operator workflow status

The issue prescribed `using-superpowers` first, with the chain
`brainstorming → writing-plans → executing-plans →
verification-before-completion → requesting-code-review`. The actual refresh
landed across multiple smaller PRs over April–May 2026 (the `2026-05-26`
last-edit timestamp on every canonical doc reflects the final consolidation
pass). Each sub-issue carried its own plan/PR pair, so the chain was followed
per-fragment rather than as one large epic — a pragmatic choice given the
breadth.

## Decision

Close #1193. The DoD is met: docs are grouped by use case, canonical files
exist and were freshly edited 2026-05-26, indexes provide discovery, all six
superseded sub-issues are closed.

## Follow-up — none

No new debt is recorded. Documentation freshness is now tracked through:

- `docs/engineering/docs-maintenance.md` — recurring docs hygiene runbook
- `docs/runbooks/README.md` — adds new runbook entries as they are written

If the runtime surface grows again, file a fresh epic rather than re-opening
#1193.
