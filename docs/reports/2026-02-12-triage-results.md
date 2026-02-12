***REMOVED*** Triage Results — 2026-02-12

**Issue:** ***REMOVED***175 | **Auditor:** Claude Opus 4.6 | **Open issues before:** 41 | **After:** 40

***REMOVED******REMOVED*** Summary

| Category | Count |
|----------|-------|
| P0-critical | 2 |
| P1-next (has PR or in-progress) | 9 |
| P2-backlog | 28 |
| Epics/meta (not prioritized) | 3 |
| Closed as duplicate | 1 (***REMOVED***192) |
| Renovate dashboard | 1 (***REMOVED***11) |

***REMOVED******REMOVED*** Labels Created

| Label | Color | Description |
|-------|-------|-------------|
| `P0-critical` | 🔴 `***REMOVED***d73a4a` | Blocking: security, CI broken, data loss |
| `P1-next` | 🟡 `***REMOVED***e4e669` | Next sprint: has PR or actively in-progress |
| `P2-backlog` | 🔵 `***REMOVED***0075ca` | Planned but not urgent |
| `has-pr` | 🟦 `***REMOVED***a2eeef` | Issue has an open pull request |

***REMOVED******REMOVED*** Full Issue Table

| ***REMOVED*** | Title | Priority | Labels Added | Status | PR | Assignee |
|---|-------|----------|-------------|--------|-----|----------|
| **P0-critical** |
| 71 | security: pin uv builder images + update minio (CVE) | P0 | P0-critical | needs-work | — | — |
| 179 | chore(ci): clean dirty worktree before baseline/verification | P0 | P0-critical | needs-work | — | — |
| **P1-next** |
| 164 | fix: chaos tests broken — LLMService API changed | P1 | P1-next, has-pr | has-PR | ***REMOVED***180 | — |
| 166 | fix(validation): add retry/timeout for external deps | P1 | P1-next, has-pr | has-PR | ***REMOVED***177 | — |
| 168 | fix(validation): relax brittle thresholds | P1 | P1-next, has-pr | has-PR | ***REMOVED***194 | — |
| 176 | bug(validation): cold cache flush uses v3 key patterns | P1 | P1-next, has-pr | has-PR | ***REMOVED***178 | — |
| 181 | fix(ci): unblock mypy in sip setup | P1 | P1-next, has-pr | has-PR | ***REMOVED***182 | — |
| 183 | fix(ci): redisvl dependency gate robust | P1 | P1-next, has-pr | has-PR | ***REMOVED***185 | — |
| 191 | chore(ci): full auto-fix sweep for unit+mypy | P1 | P1-next, has-pr | has-PR | ***REMOVED***193 | — |
| 155 | fix(vectorizers): migrate to redisvl 0.14.0 | P1 | P1-next | assigned | — | yastman |
| 189 | fix(baseline): CI baseline isolation (***REMOVED***167) | P1 | P1-next | review-needed | — | — |
| **P2-backlog: CI/test fixes** |
| 184 | test(hardening): isolate redisvl sys.modules mocks | P2 | P2-backlog | needs-work | — | — |
| 186 | test(unit): RAGPipeline default-init test isolation | P2 | P2-backlog | needs-work | — | — |
| 187 | fix(evaluation): remove import side effect extract_ground_truth | P2 | P2-backlog | needs-work | — | — |
| 188 | fix(evaluation): remove import side effect search_engines | P2 | P2-backlog | needs-work | — | — |
| **P2-backlog: Features** |
| 75 | feat: add LangGraph streaming (astream) | P2 | P2-backlog | deferred | — | yastman |
| 74 | feat: enable PostgresSaver for LangGraph persistence | P2 | P2-backlog | deferred | — | yastman |
| 152 | feat: Conversation Memory | P2 | P2-backlog | deferred | — | yastman |
| 157 | chore(memory): finalize ***REMOVED***154 | P2 | P2-backlog | assigned | — | yastman |
| 162 | feat(observability): SDK-level Redis hooks | P2 | P2-backlog | needs-work | — | — |
| 147 | feat(observability): slow-thinking latency breakdown | P2 | P2-backlog | deferred | — | yastman |
| **P2-backlog: Eval** |
| 126 | feat(eval): Langfuse gold-set dataset + experiments | P2 | P2-backlog | deferred | — | — |
| 127 | feat(eval): Langfuse LLM-as-a-Judge calibration | P2 | P2-backlog | deferred | — | — |
| **P2-backlog: Infra** |
| 54 | feat: migrate VPS stack to k3s | P2 | P2-backlog | deferred | — | — |
| 70 | feat: Qdrant snapshots for backup | P2 | P2-backlog | deferred | — | — |
| 72 | infra: BuildKit cache mounts + slim Docker images | P2 | P2-backlog | deferred | — | yastman |
| 73 | infra: k3s production tuning | P2 | P2-backlog | deferred | — | — |
| 100 | perf(embed): tail-latency guard for BGE-M3 | P2 | P2-backlog | deferred | — | — |
| 102 | perf: contingency A/B benchmark | P2 | P2-backlog | deferred | — | — |
| **P2-backlog: Kommo Agentic (milestone)** |
| 133 | [Epic] Kommo-First Agentic RAG Rollout | P2 | P2-backlog | tracking | — | — |
| 132 | Design: adopt SGR features into LangGraph RAG | P2 | P2-backlog | deferred | — | — |
| 134 | feat(input): unified inbound schema + auth | P2 | P2-backlog | deferred | — | — |
| 135 | feat(kommo): FastAPI webhook ingress | P2 | P2-backlog | deferred | — | — |
| 136 | feat(skills): modular skill packs | P2 | P2-backlog | deferred | — | — |
| 137 | feat(agent): LiteLLM tool-calling ReAct loop | P2 | P2-backlog | deferred | — | — |
| 138 | feat(tools): CRM + KB tool registry | P2 | P2-backlog | deferred | — | — |
| 139 | feat(guardrails): autonomy policy matrix | P2 | P2-backlog | deferred | — | — |
| 140 | feat(memory): 3-tier memory | P2 | P2-backlog | deferred | — | — |
| 141 | feat(observability): canonical agent trace schema | P2 | P2-backlog | deferred | — | — |
| 142 | feat(subagents): phase-2 handoff protocol | P2 | P2-backlog | deferred | — | — |
| **Not prioritized** |
| 130 | [Epic] Stack Modernization 2026 | — | — | tracking | — | — |
| 175 | chore(triage): backlog audit v2 | — | backlog | this-issue | — | — |
| 11 | Dependency Dashboard | — | dependencies | Renovate | — | — |

***REMOVED******REMOVED*** Duplicates Closed

| ***REMOVED*** | Title | Closed As | Reason |
|---|-------|-----------|--------|
| 192 | fix(validation): relax thresholds — impl ***REMOVED***168 | dup of ***REMOVED***168 | PR ***REMOVED***194 covers both |
| 174 | (closed earlier) | dup of ***REMOVED***166 | Prior triage pass |

***REMOVED******REMOVED*** Open PRs Summary

***REMOVED******REMOVED******REMOVED*** Feature PRs (7 — need review/merge)

| PR | Issue | Branch | Title |
|----|-------|--------|-------|
| ***REMOVED***194 | ***REMOVED***168 | fix/168-validation-thresholds | fix(validation): relax thresholds |
| ***REMOVED***193 | ***REMOVED***191 | fix/191-ci-green-sweep | fix(ci): restore green pipeline |
| ***REMOVED***185 | ***REMOVED***183 | fix/183-redisvl-gate | test(vectorizers): harden redisvl gate |
| ***REMOVED***182 | ***REMOVED***181 | fix/181-mypy-unblock | fix(ci): unblock mypy |
| ***REMOVED***180 | ***REMOVED***164 | fix/164-chaos-llm-api | test(chaos): fix LLM fallback suite |
| ***REMOVED***178 | ***REMOVED***176 | fix/176-cache-flush-version | fix(validation): cache version flush |
| ***REMOVED***177 | ***REMOVED***166 | fix/166-validation-retry-resilience | fix(validation): add retry/timeout |

***REMOVED******REMOVED******REMOVED*** Renovate PRs (11 — dependency updates)

| PR | Title | Age |
|----|-------|-----|
| ***REMOVED***53 | pin dependencies | old |
| ***REMOVED***50 | lock file maintenance | old |
| ***REMOVED***49 | update monitoring | old |
| ***REMOVED***48 | update docker/dockerfile tag | old |
| ***REMOVED***47 | update fastapi | old |
| ***REMOVED***46 | pin dependencies (GH Actions) | old |
| ***REMOVED***45 | pin dependencies (uv base) | old |
| ***REMOVED***42 | update clickhouse v26 | old |
| ***REMOVED***41 | update clickhouse v24.12 | old |
| ***REMOVED***31 | update python docker tag v3.14 | old |
| ***REMOVED***4 | release-please 2.14.0 | pending |

***REMOVED******REMOVED*** Recommended Next Actions

1. **Merge P1 PRs** — 7 feature PRs ready for review (***REMOVED***194, ***REMOVED***193, ***REMOVED***185, ***REMOVED***182, ***REMOVED***180, ***REMOVED***178, ***REMOVED***177)
2. **Fix P0 blockers** — ***REMOVED***71 (security CVE), ***REMOVED***179 (CI dirty worktree)
3. **Triage Renovate PRs** — 11 stale dependency PRs need `/deps` audit
4. **Verify ***REMOVED***189** — check if merged PR ***REMOVED***190 fully resolves baseline isolation
5. **Close ***REMOVED***175** — after this report is committed
