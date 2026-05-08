# Full Documentation Actualization Audit — 2026-05-08

**Scope:** All project documentation against `origin/dev` at `6391f52e`.
**Method:** Read-only file inspection, `rg` cross-reference, `make docs-check`, compose/config drift checks.
**Related:** #1396, `docs/audits/2026-05-07-project-docs-order-audit.md`

---

## Executive Summary

The docs tree has healthy top-level entrypoints (`docs/README.md`, `docs/runbooks/README.md`, `docs/engineering/docs-maintenance.md`), but **eight concrete drift items** create stale-source-of-truth risk. The most impactful are:

1. **Missing `k8s/AGENTS.override.md`** — `AGENTS.md` promises it; it does not exist.
2. **ADRS.md vs docs/adr/ mismatch** — titles and file names are crossed; readers get wrong ADR content.
3. **Onboarding docs use stale env vars** — `LITELLM_API_KEY`, `BGE_M3_URL`, and `LANGFUSE_HOST=https://cloud.langfuse.com` do not match current compose/contracts.
4. **Docs-check not in CI** — `make docs-check` passes today but is not enforced in `.github/workflows/ci.yml`.
5. **Old plans reference unexecuted moves** — `docs/superpowers/plans/2026-04-01-file-structure-reorganization-plan.md` describes moving `AGENTS.override.md` to `.claude/rules/features/`, which was never done.
6. **Cache and developer-guide duplication** — three cache docs and two "add node" guides duplicate each other.
7. **Audits README missing recent audits** — `docs/audits/README.md` omits the `2026-05-07-project-docs-order-audit.md` entry.
8. **Stale `.claude/rules/` links still present** — five broken links reported in the 2026-05-07 audit are still unfixed.

**Risk level:** MEDIUM-HIGH. The missing `k8s/AGENTS.override.md` and ADR mismatch directly mislead agents. Onboarding stale env vars waste new-developer time.

---

## Verification Commands Run

```bash
# 1. Docs directory structure
find docs -maxdepth 2 -type d | sort
# → docs/indexes/ exists (correct); no unexpected dirs

# 2. Markdown file inventory
rg --files docs README.md AGENTS.md DOCKER.md services telegram_bot src mini_app k8s | rg '(^README.md$|AGENTS.md$|DOCKER.md$|README.md$|\.md$)' | sort
# → 108 markdown files; all expected paths present

# 3. Key term cross-reference
rg -n "docs/indexes|runbooks|QDRANT|Redis|Langfuse|LiteLLM|Docker|compose|validate-traces|make docs-check" README.md AGENTS.md DOCKER.md docs services telegram_bot src mini_app k8s
# → All major terms resolve to canonical docs

# 4. make docs-check
make docs-check
# → exit 0; "All relative Markdown links OK"
# NOTE: This only checks relative link existence, not conceptual accuracy.

# 5. git diff --check
git diff --check
# → clean (no trailing whitespace or conflict markers)

# 6. Compose service list vs DOCKER.md
python3 -c "import yaml; print('\n'.join(sorted(yaml.safe_load(open('compose.yml'))['services'].keys())))"
# → 22 services; DOCKER.md profile table matches

# 7. AGENTS.override.md inventory
find . -maxdepth 3 -name 'AGENTS.override.md' | sort
# → telegram_bot/AGENTS.override.md
# → src/ingestion/unified/AGENTS.override.md
# → k8s/AGENTS.override.md  MISSING

# 8. Recent git history for docs
git log --oneline --since='2026-03-01' --until='2026-05-09' -- docs/ | wc -l
# → 35 commits; active docs maintenance

# 9. Broken .claude/rules/ links (still present)
rg -n '\.claude/' docs/ README.md DOCKER.md AGENTS.md | grep -v superpowers
# → 5 hits in HITL.md, API_REFERENCE.md, BOT_INTERNAL_STRUCTURE.md, ONBOARDING.md
```

---

## Drift Findings

### 1. Missing `k8s/AGENTS.override.md`

| | |
|---|---|
| **Evidence** | `AGENTS.md:129` lists `k8s/AGENTS.override.md` under Local Overrides. `find . -maxdepth 3 -name 'AGENTS.override.md'` returns only two files. |
| **Why stale** | The file was never created, or was removed without updating `AGENTS.md`. |
| **Canonical owner** | `AGENTS.md` |
| **Proposed fix** | Create `k8s/AGENTS.override.md` scoped to k8s manifests, or remove the listing from `AGENTS.md` if k8s intentionally shares root rules. |
| **Priority** | P1 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `k8s/AGENTS.override.md` or `AGENTS.md` |

### 2. ADRS.md titles do not match docs/adr/ files

| | |
|---|---|
| **Evidence** | `docs/ADRS.md` says ADR-001 is "TypedDict for Graph State", but `docs/adr/0001-colbert-reranking.md` is about ColBERT. All six ADRs are crossed (see `docs/audits/2026-05-07-project-docs-order-audit.md` §4.1 for full table). |
| **Why stale** | `ADRS.md` was written as a standalone summary and never reconciled with the numbered ADR files created later. |
| **Canonical owner** | `docs/adr/0001-*.md` … `0006-*.md` and `docs/adr/README.md` |
| **Proposed fix** | Convert `docs/ADRS.md` to a lightweight index linking to `docs/adr/000*.md`, or archive it and redirect to `docs/adr/README.md`. |
| **Priority** | P1 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `docs/ADRS.md`, `docs/adr/README.md` |

### 3. Onboarding docs contain stale env variable names

| | |
|---|---|
| **Evidence** | `docs/ONBOARDING.md:46` uses `LITELLM_API_KEY=your_litellm_api_key`; `docs/ONBOARDING.md:54` uses `BGE_M3_URL=http://localhost:8000`; `docs/ONBOARDING.md:51` uses `LANGFUSE_HOST=https://cloud.langfuse.com`. Current compose and `DOCKER.md` use `LITELLM_MASTER_KEY`, `OPENAI_API_KEY` (or `CEREBRAS_API_KEY`/`GROQ_API_KEY`), and local Langfuse at `http://localhost:3001`. |
| **Why stale** | `ONBOARDING.md` predates the compose secret cleanup and LiteLLM proxy contract changes. |
| **Canonical owner** | `docs/LOCAL-DEVELOPMENT.md`, `DOCKER.md`, `compose.yml` |
| **Proposed fix** | Rewrite `ONBOARDING.md` as a redirect/checklist page linking to `LOCAL-DEVELOPMENT.md`. Same for `ONBOARDING_CHECKLIST.md`. |
| **Priority** | P1 |
| **Langfuse #1367** | Can piggyback if onboarding is touched; otherwise separate docs PR |
| **Reserved files** | `docs/ONBOARDING.md`, `docs/ONBOARDING_CHECKLIST.md` |

### 4. `make docs-check` not enforced in CI

| | |
|---|---|
| **Evidence** | `Makefile:481-483` defines `docs-check`. `rg -n 'docs-check' .github/workflows/ci.yml` returns nothing. |
| **Why stale** | The target was added locally but never wired into CI, so future broken links can merge undetected. |
| **Canonical owner** | `.github/workflows/ci.yml`, `Makefile` |
| **Proposed fix** | Add `make docs-check` as a CI job step (fast, zero secrets). |
| **Priority** | P1 |
| **Langfuse #1367** | Separate docs PR (CI-only, no runtime impact) |
| **Reserved files** | `.github/workflows/ci.yml` |

### 5. Old plans reference unexecuted `.claude/rules/features/` move

| | |
|---|---|
| **Evidence** | `docs/superpowers/plans/2026-04-01-file-structure-reorganization-plan.md:125-149` plans to move `src/ingestion/unified/AGENTS.override.md` to `.claude/rules/features/ingestion-unified.md`. The directory `.claude/rules/features/` does not exist. The move was never executed, but the plan is not marked abandoned. |
| **Why stale** | Plans should be marked archive/reference-only when superseded or abandoned. |
| **Canonical owner** | `docs/superpowers/plans/2026-04-01-file-structure-reorganization-plan.md` |
| **Proposed fix** | Add an archive banner at the top of the plan (and the matching design spec) stating the move was abandoned and `AGENTS.override.md` remains in tree. |
| **Priority** | P2 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `docs/superpowers/plans/2026-04-01-file-structure-reorganization-plan.md`, `docs/superpowers/specs/2026-04-01-file-structure-reorganization-design.md` |

### 6. Cache documentation triplicate (still unresolved from 2026-05-07 audit)

| | |
|---|---|
| **Evidence** | `docs/TROUBLESHOOTING_CACHE.md` (188 lines), `docs/CACHE_DEGRADATION.md` (93 lines), and `docs/runbooks/REDIS_CACHE_DEGRADATION.md` all define cache tiers, thresholds, and degradation modes. Threshold values appear in multiple files. |
| **Why stale** | No canonical consolidation was done after the 2026-05-07 audit flagged it. |
| **Canonical owner** | `docs/runbooks/REDIS_CACHE_DEGRADATION.md` (already links to source files) |
| **Proposed fix** | Merge tier definitions into `docs/runbooks/REDIS_CACHE_DEGRADATION.md`. Archive or redirect the other two. |
| **Priority** | P2 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `docs/TROUBLESHOOTING_CACHE.md`, `docs/CACHE_DEGRADATION.md`, `docs/runbooks/REDIS_CACHE_DEGRADATION.md` |

### 7. `docs/DEVELOPER_GUIDE.md` duplicates `docs/ADD_NEW_RAG_NODE.md`

| | |
|---|---|
| **Evidence** | `docs/DEVELOPER_GUIDE.md` (243 lines) includes a full "Adding a New LangGraph Node" section. `docs/ADD_NEW_RAG_NODE.md` is a dedicated guide for the same task. Both describe `telegram_bot/graph/nodes/`, `build_graph()`, and state contract. |
| **Why stale** | Two owners for the same fact. |
| **Canonical owner** | `docs/ADD_NEW_RAG_NODE.md` (more detailed and focused) |
| **Proposed fix** | Trim `DEVELOPER_GUIDE.md` to a redirect/index or archive it. Keep `ADD_NEW_RAG_NODE.md` as the canonical guide. |
| **Priority** | P2 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `docs/DEVELOPER_GUIDE.md`, `docs/ADD_NEW_RAG_NODE.md` |

### 8. `docs/audits/README.md` missing recent audit entries

| | |
|---|---|
| **Evidence** | `docs/audits/README.md` lists audits up to `2026-05-08-telethon-langfuse-runtime-loop.md` but omits `docs/audits/2026-05-07-project-docs-order-audit.md` and the current audit file. |
| **Why stale** | Audits README was last updated before the 2026-05-07 project-docs-order audit was merged. |
| **Canonical owner** | `docs/audits/README.md` |
| **Proposed fix** | Append the missing 2026-05-07 and 2026-05-08 audit entries. |
| **Priority** | P0 (trivial, safe, should be done before this audit PR merges) |
| **Langfuse #1367** | Can be included in this audit PR |
| **Reserved files** | `docs/audits/README.md` |

### 9. Broken `.claude/rules/` links still present (from 2026-05-07 audit)

| | |
|---|---|
| **Evidence** | Same five broken links documented in `docs/audits/2026-05-07-project-docs-order-audit.md` §5.3: `docs/HITL.md:137`, `docs/API_REFERENCE.md:205`, `docs/BOT_INTERNAL_STRUCTURE.md:176`, `docs/ONBOARDING.md:171-172`, `docs/ONBOARDING.md:178`. `make docs-check` does NOT catch these because the checker only validates relative links to files that exist within the repo tree; `.claude/rules/` was removed from the tree. |
| **Why stale** | The `.claude/rules/` directory was retired; docs still reference it. |
| **Canonical owner** | Each affected doc |
| **Proposed fix** | Replace links with nearest equivalent (`telegram_bot/AGENTS.override.md`, `docs/runbooks/README.md`, or remove). |
| **Priority** | P1 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `docs/HITL.md`, `docs/API_REFERENCE.md`, `docs/BOT_INTERNAL_STRUCTURE.md`, `docs/ONBOARDING.md` |

### 10. `docs/ONBOARDING_CHECKLIST.md` duplicates `docs/LOCAL-DEVELOPMENT.md`

| | |
|---|---|
| **Evidence** | `docs/ONBOARDING_CHECKLIST.md` repeats `make local-up`, `make test-bot-health`, `make run-bot`, `make check`, `make test-unit`, env copy steps, and service startup instructions already canonical in `docs/LOCAL-DEVELOPMENT.md`. |
| **Why stale** | Same duplication pattern as `ONBOARDING.md`. |
| **Canonical owner** | `docs/LOCAL-DEVELOPMENT.md` |
| **Proposed fix** | Convert to a checklist-only page linking to `LOCAL-DEVELOPMENT.md` and `DOCKER.md`. |
| **Priority** | P2 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `docs/ONBOARDING_CHECKLIST.md` |

### 11. `docs/ADR.md` vs `docs/adr/README.md` duplication

| | |
|---|---|
| **Evidence** | `docs/adr/README.md` is a clean index. `docs/ADRS.md` is a long prose file with mismatched ADR content. Both claim to be the ADR entrypoint. |
| **Why stale** | `ADRS.md` was written before `adr/README.md` existed; they were never reconciled. |
| **Canonical owner** | `docs/adr/README.md` |
| **Proposed fix** | Archive or redirect `docs/ADRS.md` to `docs/adr/README.md`. |
| **Priority** | P1 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `docs/ADRS.md`, `docs/adr/README.md` |

### 12. Some March 2026 SDK migration plans may need archive banners

| | |
|---|---|
| **Evidence** | `docs/plans/2026-03-13-sdk-first-remediation-plan.md`, `docs/plans/2026-03-15-sdk-canonical-remediation-plan.md`, and related audit reports (`SDK_MIGRATION_AUDIT_2026-03-13.md`, `SDK_MIGRATION_ROADMAP_2026-03-13.md`) describe work that appears completed based on `docs/SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md`. The plans are not marked archive/reference-only. |
| **Why stale** | Plans that are fully executed should carry an archive banner so agents do not treat them as active backlog. |
| **Canonical owner** | `docs/plans/` directory index or each plan file |
| **Proposed fix** | Add archive banners to completed March 2026 SDK migration plans and audit reports. |
| **Priority** | P2 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `docs/plans/2026-03-13-*.md`, `docs/plans/2026-03-15-*.md`, `docs/SDK_MIGRATION_AUDIT_2026-03-13.md`, `docs/SDK_MIGRATION_ROADMAP_2026-03-13.md` |

### 13. `README.md` Quick Start still duplicates `DOCKER.md` profile matrix

| | |
|---|---|
| **Evidence** | `README.md:192-218` includes `make local-up`, `make test-bot-health`, `make run-bot`, `make docker-bot-up`, `make docker-full-up`, and an Optional Stacks table. These are canonical in `DOCKER.md` and `docs/LOCAL-DEVELOPMENT.md`. |
| **Why stale** | Root README should be an elevator pitch, not a duplicate operations manual. This was noted in the 2026-05-07 audit Wave 1. |
| **Canonical owner** | `DOCKER.md`, `docs/LOCAL-DEVELOPMENT.md` |
| **Proposed fix** | Replace the commands table in `README.md` with a single link to `DOCKER.md` and `docs/LOCAL-DEVELOPMENT.md`. Keep only the three most common one-liners. |
| **Priority** | P2 |
| **Langfuse #1367** | Separate docs PR |
| **Reserved files** | `README.md` |

---

## Proposed Fix Worker Waves

These waves are disjoint; each can be assigned to a separate worker without file conflicts.

### Wave A — Critical Fixes (P0/P1, small blast radius)

| Worker | Files | Task |
|---|---|---|
| `W-docs-k8s-agents-override` | `k8s/AGENTS.override.md` (new) or `AGENTS.md` | Create missing override or remove listing. |
| `W-docs-adr-reconcile` | `docs/ADRS.md`, `docs/adr/README.md` | Convert ADRS.md to index or archive; ensure titles match `000*.md`. |
| `W-docs-onboarding-stale-env` | `docs/ONBOARDING.md`, `docs/ONBOARDING_CHECKLIST.md` | Replace stale env vars with canonical references to `LOCAL-DEVELOPMENT.md`. |
| `W-docs-broken-claude-links` | `docs/HITL.md`, `docs/API_REFERENCE.md`, `docs/BOT_INTERNAL_STRUCTURE.md`, `docs/ONBOARDING.md` | Fix/remove `.claude/rules/` links. |
| `W-docs-audits-index` | `docs/audits/README.md` | Add missing 2026-05-07 and 2026-05-08 audit entries. |
| `W-docs-ci-docs-check` | `.github/workflows/ci.yml` | Add `make docs-check` to CI. |

### Wave B — Consolidation (P2, medium blast radius)

| Worker | Files | Task |
|---|---|---|
| `W-docs-cache-consolidate` | `docs/CACHE_DEGRADATION.md`, `docs/TROUBLESHOOTING_CACHE.md`, `docs/runbooks/REDIS_CACHE_DEGRADATION.md` | Merge tier definitions into runbook; archive others. |
| `W-docs-dev-guide-dedup` | `docs/DEVELOPER_GUIDE.md`, `docs/ADD_NEW_RAG_NODE.md` | Deduplicate node-creation guidance. |
| `W-docs-readme-dedup` | `README.md` | Trim Quick Start duplication; link to canonical docs. |
| `W-docs-archive-old-plans` | `docs/plans/2026-03-13-*.md`, `docs/plans/2026-03-15-*.md`, `docs/SDK_MIGRATION_*_2026-03-13.md`, `docs/superpowers/plans/2026-04-01-file-structure-reorganization-plan.md`, `docs/superpowers/specs/2026-04-01-file-structure-reorganization-design.md` | Add archive banners to completed/abandoned plans. |

### Wave C — Index Hygiene (P2, small blast radius)

| Worker | Files | Task |
|---|---|---|
| `W-docs-folder-readme-search` | `src/README.md`, `tests/README.md`, `scripts/README.md` | Add fast-search `rg` recipes where missing. |

---

## Langfuse #1367 Closure Recommendation

Langfuse #1367 (OpenAI auto-tracing fix) is a runtime change. Docs impact is minimal:
- `docs/engineering/sdk-registry.md` already documents `langfuse.openai.AsyncOpenAI` as the canonical path.
- `docs/LOCAL-DEVELOPMENT.md` and `DOCKER.md` do not need changes.

**Recommendation:** Do not block #1367 closure on docs fixes. All audit findings should be addressed in a separate `docs/actualization-2026-05` PR after #1367 merges.

---

## Appendix: Files Inspected

```
README.md
AGENTS.md
DOCKER.md
docs/README.md
docs/LOCAL-DEVELOPMENT.md
docs/ONBOARDING.md
docs/ONBOARDING_CHECKLIST.md
docs/PROJECT_STACK.md
docs/BOT_ARCHITECTURE.md
docs/BOT_INTERNAL_STRUCTURE.md
docs/PIPELINE_OVERVIEW.md
docs/TROUBLESHOOTING_CACHE.md
docs/CACHE_DEGRADATION.md
docs/runbooks/README.md
docs/runbooks/REDIS_CACHE_DEGRADATION.md
docs/ADRS.md
docs/adr/README.md
docs/adr/0001-colbert-reranking.md
docs/adr/0002-bge-m3-embeddings.md
docs/DEVELOPER_GUIDE.md
docs/ADD_NEW_RAG_NODE.md
docs/API_REFERENCE.md
docs/HITL.md
docs/engineering/sdk-registry.md
docs/engineering/test-writing-guide.md
docs/engineering/issue-triage.md
docs/engineering/docs-maintenance.md
docs/indexes/README.md
docs/indexes/fast-search.md
docs/indexes/runtime-services.md
docs/indexes/observability-and-storage.md
docs/audits/README.md
docs/audits/2026-05-07-project-docs-order-audit.md
docs/superpowers/plans/2026-04-01-file-structure-reorganization-plan.md
docs/superpowers/specs/2026-04-01-file-structure-reorganization-design.md
telegram_bot/AGENTS.override.md
telegram_bot/README.md
src/ingestion/unified/AGENTS.override.md
src/README.md
src/api/README.md
services/README.md
mini_app/README.md
k8s/README.md
tests/README.md
docker/README.md
scripts/README.md
Makefile
.github/workflows/ci.yml
compose.yml
compose.dev.yml
compose.vps.yml
```
