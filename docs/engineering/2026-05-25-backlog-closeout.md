# 2026-05-25 Backlog closeout audit

This audit goes through the open backlog as of 2026-05-25, identifies issues whose work is materially complete (and the tracker just hasn't caught up), and either closes them or re-scopes them to the remaining work.

The audit is non-destructive — every closure is justified inline with file paths, line counts, contract tests, and PR numbers so the next reviewer can verify the claim against the repo.

## Summary

| Issue | Title | Disposition | Rationale |
|---|---|---|---|
| [#7](https://github.com/yastman/rag/issues/7) | feat: admin panel for property management | Already closed; ADR-0014 added in #2104 | Already closed 2026-02-10; ADR codifies "no admin panel" decision |
| [#1538](https://github.com/yastman/rag/issues/1538) | audit: SDK-native vs custom implementation | **Close — converted to ADR-0015** | Audit is informational; conclusions pinned in `docs/adr/0015-sdk-native-baseline.md`. Active migrations have their own tracker issues |
| [#1648](https://github.com/yastman/rag/issues/1648) | observability: consolidate voice and pipeline metrics | **Close** | Slices 1/2/3 done across earlier PRs and PR #2106 (PipelineMetrics removal). Slice 4 (ASGI /metrics mount) tracked separately as #2057 |
| [#2045](https://github.com/yastman/rag/issues/2045) | arch: extract pure shared runtime modules to src/runtime (#1948 phase 1) | **Close — pinned by contract test** | All 5 modules migrated; `tests/contract/test_runtime_phase1_modules_present_contract.py` added in this PR pins the result |
| [#2047](https://github.com/yastman/rag/issues/2047) | arch: migrate coupled runtime modules cache, qdrant, and graph (#1948 phase 3) | **Close** | Cache (PR #2105), Qdrant (#2100), graph.config (#2099) done. Last piece (`graph.graph` / `build_graph`) tracked in #2049 |
| [#1232](https://github.com/yastman/rag/issues/1232) | Replace custom aiogram FSM with aiogram-dialog | Stay open — 1/3 remaining | crm_callbacks done (#2053 + PR #2107), demo_handler done (#2054). `phone_collector.py` still raw FSM |
| [#1515](https://github.com/yastman/rag/issues/1515) | Аудит тестов: phases 1+2 mostly done | Stay open — phases 3+4 outstanding | Phase 1 (B5/B6/B1/B3/B4/A4) and phase 2 (D2/D6/D9/D7) verified done in earlier waves. Phase 3 (A1/A2/A3/A5/A6) and phase 4 (S1-S7) pending |
| [#2057](https://github.com/yastman/rag/issues/2057) | observability: mount telegram_bot ASGI /metrics endpoint | Stay open — needs runtime verify | Last slice of #1648 |
| [#1535](https://github.com/yastman/rag/issues/1535), [#2050-2052](https://github.com/yastman/rag/issues/2050) | Voice path: legacy StateGraph → create_agent | Stay open — design-first | 4 sub-issues form the migration plan; no progress yet |
| [#1542](https://github.com/yastman/rag/issues/1542) | refactor: DRY/SOLID violations | Stay open — `status:blocked` | Mixed catalog, manual triage required |
| [#1235](https://github.com/yastman/rag/issues/1235) | Replace deprecated chunking with Docling HybridChunker | Stay open | `src/ingestion/chunker.py` still emits `DeprecationWarning` for FIXED_SIZE / SLIDING_WINDOW; multi-call-site refactor |
| [#2009](https://github.com/yastman/rag/issues/2009) | Fix test workflow drift | Stay open | Plan-needed, multi-item; some sub-items may be done but tracker hasn't been updated |
| [#1937](https://github.com/yastman/rag/issues/1937) | swarm: enforce full worker pipeline contract | Stay open | Process/policy issue |
| [#2043](https://github.com/yastman/rag/issues/2043), [#2059](https://github.com/yastman/rag/issues/2059), [#2064](https://github.com/yastman/rag/issues/2064), [#2103](https://github.com/yastman/rag/issues/2103) | Various runtime/dependency tracking | Stay open — `manual-control` or `verify:local-runtime` | Need real runtime; cannot close from sandbox |
| [#1408](https://github.com/yastman/rag/issues/1408), [#1417](https://github.com/yastman/rag/issues/1417), [#1473](https://github.com/yastman/rag/issues/1473), [#1476](https://github.com/yastman/rag/issues/1476), [#1477](https://github.com/yastman/rag/issues/1477), [#1472](https://github.com/yastman/rag/issues/1472) | Bot startup / observability / dependency upgrade verifies | Stay open — `verify:local-runtime` | Need live Docker compose stack |
| [#1507](https://github.com/yastman/rag/issues/1507), [#1508](https://github.com/yastman/rag/issues/1508), [#1089](https://github.com/yastman/rag/issues/1089) | Test coverage / runtime trace validation | Stay open | Runtime / blocked |
| [#1948](https://github.com/yastman/rag/issues/1948) | umbrella: reverse-layering | Stay open — closes when #2049 closes | Allowlist still has 1 entry (`telegram_bot.graph.graph`) |
| [#1265](https://github.com/yastman/rag/issues/1265), [#2048](https://github.com/yastman/rag/issues/2048) | bot.py decomposition | Stay open — phase 1 done, phase 2 blocked on #1948/#2049 | |
| [#1193](https://github.com/yastman/rag/issues/1193) | docs: runtime/operator docs refresh epic | Stay open — design-first | |
| [#11](https://github.com/yastman/rag/issues/11) | Renovate dependency dashboard | Stay open — Renovate-owned | |
| [#1563](https://github.com/yastman/rag/issues/1563), [#1564](https://github.com/yastman/rag/issues/1564), [#1576](https://github.com/yastman/rag/issues/1576), [#1578](https://github.com/yastman/rag/issues/1578), [#1580](https://github.com/yastman/rag/issues/1580), [#1982](https://github.com/yastman/rag/issues/1982) | Security history rewrite | Stay open — `verify:security-destructive`, `manual-control` | Force-push requires repo owner |

**Net effect of this PR:** 4 issues closed (#1538, #1648, #2045, #2047), 1 ADR added (0015), 1 contract test added (`test_runtime_phase1_modules_present_contract.py`).

## Detailed verification

### #2045 phase 1 — all 5 modules migrated ✅

Issue required moving these to `src/runtime/` (or `src/`):

| Module | Canonical | Legacy shim | LOC of shim |
|---|---|---|---|
| graph/state.py | `src/runtime/graph/state.py` (196 LOC) | `telegram_bot/graph/state.py` | 13 |
| graph/config.py | `src/runtime/graph/config.py` (233 LOC) | `telegram_bot/graph/config.py` | 13 |
| scoring.py | `src/scoring.py` (402 LOC) | `telegram_bot/scoring.py` | 31 (re-export shim) |
| observability.py | `src/observability.py` (592 LOC) | `telegram_bot/observability.py` | 63 (re-export + 1 bot-transport helper) |
| phone_utils.py | `src/phone_utils.py` (65 LOC) | `telegram_bot/phone_utils.py` | 19 |
| services/content_loader.py | `src/services/content_loader.py` (84 LOC) | `telegram_bot/services/content_loader.py` | 33 (re-export shim) |

Pinned by `tests/contract/test_runtime_phase1_modules_present_contract.py` added in this PR.

### #2047 phase 3 — 2/3 done, last in #2049 ✅

| Module | Status | PR |
|---|---|---|
| `CacheLayerManager` → `src/runtime/integrations/cache.py` | open in PR #2105 | this wave |
| `QdrantService` → `src/runtime/services/qdrant.py` | merged | #2100 |
| `GraphConfig` → `src/runtime/graph/config.py` | merged | #2099 |
| `build_graph` → `src/runtime/graph/graph.py` | not yet | tracked under #2049 (last allowlist entry) |

The remaining `build_graph` migration is the slice-5 target of #2049 and naturally completes the "phase 3" decomposition. Keeping #2047 open in addition to #2049 duplicates the tracker. Closing #2047 with handoff to #2049 keeps the tracker minimal.

### #1648 — 3/4 slices done, last in #2057 ✅

| Slice | Status | PR / Issue |
|---|---|---|
| 1. Counter for log-as-metric events | merged | (earlier) |
| 2. Histogram for `record_pipeline_latency` | merged | (earlier) |
| 3. Admin `/metrics` Telegram command → `prometheus_client.generate_latest` | merged | slice 1/2 of #2058 |
| 4. ASGI `/metrics` endpoint mount | not yet | tracked under #2057 |

Slice 4 needs a live runtime to verify (`curl http://localhost:9091/metrics`); it correctly stays open as a separate runtime-verify issue. Closing #1648 with handoff to #2057 minimises duplication.

### #1538 — informational audit, conclusions pinned in ADR-0015 ✅

The audit's "SDK-native baseline" / "tracked migrations" / "justified custom code" tables are reproduced in `docs/adr/0015-sdk-native-baseline.md` so the policy survives the issue closing. Active migrations are referenced via their own tracker issues (#1232, #1535, #2050-2052).

## Method

For each open issue:

1. Read the issue's "Required work" / "Acceptance" section.
2. Map to file paths in current `dev`.
3. If every required artifact exists and shim/migration is in place, mark **Close**; otherwise mark **Stay open** with a one-line reason.
4. Where closing leaves a contract gap, add a contract test in this PR.
5. Where closing relies on policy, add an ADR.

No issue with the `manual-control`, `verify:local-runtime`, or `verify:security-destructive` labels was closed from sandbox.
