# Project Documentation Order Audit — 2026-05-07

**Scope:** `docs/`, root `README.md`, `DOCKER.md`, `AGENTS.md`, folder `README.md` files, and `AGENTS.override.md` files.
**Method:** Read current files, exact `rg` searches, relative-link existence checks. No code, Compose, or runtime changes.
**Related:** #1396

---

## 1. Executive Summary

The docs tree is well-organized at the top level (`docs/README.md`, `docs/runbooks/README.md`, `docs/engineering/`), but **three stale-doc risk areas** and **two duplicate-truth risks** create drift. Several broken links point to a retired `.claude/rules/` path. Folder READMEs are generally healthy, but a few lack fast-search recipes. No automated link checker is in place.

**Risk level:** MEDIUM. The core entrypoints (`docs/README.md`, `docs/runbooks/README.md`, `DOCKER.md`, `docs/LOCAL-DEVELOPMENT.md`) are current, but duplication increases the cost of every env/compose change.

---

## 2. Methodology

Commands run during this audit (representative sample):

```bash
rg -n -i "source of truth|canonical|compose project name|worktree-named" docs/ README.md DOCKER.md
rg -n "make docker-up|make local-up|make check|make test-unit|make test-bot-health" docs/ README.md DOCKER.md
rg -n "\.claude/" docs/ README.md
find . -maxdepth 3 -name 'AGENTS.override.md' -o -name 'README.md' | sort
rg -n "TROUBLESHOOTING_CACHE|CACHE_DEGRADATION|REDIS_CACHE_DEGRADATION" docs/ README.md
rg -n "BOT_ARCHITECTURE|BOT_INTERNAL_STRUCTURE|PROJECT_STACK|PIPELINE_OVERVIEW" docs/ README.md
```

All claims below are backed by current file contents or command output.

---

## 3. Stale-Doc Risk Areas

### 3.1 Onboarding / Local-Development / README overlap

Five documents describe the same local setup steps (env copy, `make docker-up`, `make test-bot-health`, validation ladder):

- `README.md` (root) — lines 184–199, 279–280
- `docs/LOCAL-DEVELOPMENT.md` — lines 11–82, 127–128
- `docs/ONBOARDING.md` — lines 28–72, 176–178
- `docs/ONBOARDING_CHECKLIST.md` — lines 28–71, 87–93
- `DOCKER.md` — lines 35–62, 136–154

**Impact:** When a make target, env variable, or port changes, up to five files may need edits. The probability of at least one staying stale is high.

**Mitigation in place:** `DOCKER.md` and `docs/LOCAL-DEVELOPMENT.md` already declare themselves canonical. The risk is that the other three files still duplicate the instructions instead of linking.

### 3.2 Cache documentation triplicate

Three docs cover cache tiers, thresholds, and degradation:

- `docs/TROUBLESHOOTING_CACHE.md` — 188 lines; focused on debug recipes
- `docs/CACHE_DEGRADATION.md` — 93 lines; focused on tier definitions and degradation modes
- `docs/runbooks/REDIS_CACHE_DEGRADATION.md` — runbook format; focused on operator response

**Impact:** Threshold values and version prefixes (`v5`, `v8`) appear in multiple files. A bump in `integrations/cache.py` may not propagate to all three.

### 3.3 Architecture docs without clear boundaries

Four docs describe system architecture:

- `docs/PROJECT_STACK.md` — high-level subsystem map
- `docs/BOT_ARCHITECTURE.md` — bot layer architecture
- `docs/BOT_INTERNAL_STRUCTURE.md` — bot internal components
- `docs/PIPELINE_OVERVIEW.md` — ingestion, query, and voice runtime flows

They cross-reference each other (e.g., `BOT_INTERNAL_STRUCTURE.md:178` → `PIPELINE_OVERVIEW.md`), but there is no explicit boundary rule telling authors which doc owns which kind of change.

---

## 4. Duplicate Source-of-Truth Risks

### 4.1 ADRS.md vs docs/adr/

`docs/ADRS.md` contains six ADRs with titles and dates that differ from the canonical files in `docs/adr/`:

| ADRS.md entry | docs/adr/ file | Match? |
|---|---|---|
| ADR-001: TypedDict for Graph State | `0001-colbert-reranking.md` | **No** |
| ADR-002: RRF Fusion over Semantic Search Only | `0002-bge-m3-embeddings.md` | **No** |
| ADR-003: RedisVL for Semantic Cache | `0003-langgraph-voice-text-split.md` | **No** |
| ADR-004: Interrupt-based HITL Pattern | `0004-redisvl-semantic-cache.md` | **No** |
| ADR-005: BGE-M3 for All Embeddings | `0005-hybrid-search-rrf.md` | **No** |
| ADR-006: LiteLLM for LLM Abstraction | `0006-kommo-crm.md` | **No** |

**Impact:** `docs/adr/` is the canonical directory (file names are stable, referenced from plans), but `ADRS.md` presents itself as an authoritative list. A reader may trust the summary and never open the canonical files.

### 4.2 Developer guide vs add-new-node guide

- `docs/DEVELOPER_GUIDE.md` — 243 lines; includes LangGraph node creation, state contract, registration
- `docs/ADD_NEW_RAG_NODE.md` — dedicated guide for the same task

Both describe creating a node in `telegram_bot/graph/nodes/`, registering it in `build_graph()`, and updating state. The dedicated guide is more detailed, but `DEVELOPER_GUIDE.md` does not redirect to it.

---

## 5. Missing Quick-Search Paths

### 5.1 No consolidated cross-cutting search recipes in `docs/engineering/`

`docs/runbooks/README.md` provides `rg` recipes for traces, Redis, and Qdrant, but there is no equivalent in `docs/engineering/` for cross-cutting code searches (e.g., "find all LiteLLM provider keys", "find all collection name references").

### 5.2 Some folder READMEs lack fast-search sections

Healthy examples (`services/README.md`, `telegram_bot/README.md`, `mini_app/README.md`) include focused checks and `rg` recipes. Others (`src/README.md`, `tests/README.md`, `scripts/README.md`) are minimal indexes without search helpers.

### 5.3 No automated link checker

Broken relative links were found manually:

| File | Broken link | Target missing |
|---|---|---|
| `docs/HITL.md:137` | `.claude/rules/features/telegram-bot.md` | yes |
| `docs/API_REFERENCE.md:205` | `.claude/rules/features/telegram-bot.md` | yes |
| `docs/BOT_INTERNAL_STRUCTURE.md:176` | `.claude/rules/features/telegram-bot.md` | yes |
| `docs/ONBOARDING.md:171–172` | `.claude/rules/troubleshooting.md` | yes |
| `docs/ONBOARDING.md:178` | `.claude/rules/features/telegram-bot.md` | yes |

A CI-level markdown link checker (or a `make docs-check` target) would catch these before merge.

---

## 6. Docs Lookup Order

Agents and workers should use this lookup order when answering questions or updating documentation:

1. **Project indexes first** — `docs/README.md`, `docs/runbooks/README.md`, nearest folder `README.md`
2. **Nearest README / `AGENTS.override.md` second** — local subsystem rules and boundaries
3. **Current code / config third** — the running source of truth for ports, env vars, service names, routes
4. **Official docs / Context7 fourth** — for SDK/framework version-sensitive behavior
5. **Broad web / Exa only as fallback** — when the above four layers do not answer the question

`AGENTS.md` should stay a **gateway**, not a duplicated operations manual. Navigation and detailed guidance belong in the indexes (`docs/README.md`, `docs/runbooks/README.md`) and folder READMEs.

---

## 7. Recommended Follow-Up Waves

### Wave 1 — Onboarding / env deduplication (small, safe)

- Make `docs/LOCAL-DEVELOPMENT.md` the single canonical local-setup doc.
- Convert `docs/ONBOARDING.md` and `docs/ONBOARDING_CHECKLIST.md` into **redirect/checklist-only** pages that link to `LOCAL-DEVELOPMENT.md` and `DOCKER.md`.
- Remove duplicate `make` command matrices from `README.md` and link to `DOCKER.md`.

### Wave 2 — Cache docs consolidation (medium)

- Merge tier definitions and thresholds into **one canonical doc** (prefer `docs/runbooks/REDIS_CACHE_DEGRADATION.md` because it already links to source files).
- Convert `docs/TROUBLESHOOTING_CACHE.md` and `docs/CACHE_DEGRADATION.md` into runbook appendices or archive them.

### Wave 3 — ADR reconciliation (small)

- Either:
  - **Option A:** Make `docs/ADRS.md` a lightweight index that links to `docs/adr/000*.md` and nothing more.
  - **Option B:** Archive `docs/ADRS.md` and update `docs/README.md` to point directly to `docs/adr/`.

### Wave 4 — Architecture doc boundaries (medium, needs design)

- Add a one-paragraph "Ownership" header to each of the four architecture docs defining what kind of change belongs there.
- Example rule: `PROJECT_STACK.md` owns subsystem boundaries; `PIPELINE_OVERVIEW.md` owns runtime flow; `BOT_ARCHITECTURE.md` owns Telegram-layer design; `BOT_INTERNAL_STRUCTURE.md` owns file-level component map.

### Wave 5 — Broken-link cleanup and automation (small)

- Fix the five broken `.claude/rules/` links listed in §5.3.
- Evaluate adding a `make docs-check` target (e.g., `markdown-link-check` or a lightweight Python script) to CI.

### Wave 6 — Folder README search recipes (small, incremental)

- Add a "Fast Search" or `rg` recipe section to `src/README.md`, `tests/README.md`, and `scripts/README.md`, following the pattern in `services/README.md`.

---

## 8. Appendix: Files Inspected

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
docs/adr/0001-colbert-reranking.md
docs/adr/0002-bge-m3-embeddings.md
docs/adr/0003-langgraph-voice-text-split.md
docs/adr/0004-redisvl-semantic-cache.md
docs/adr/0005-hybrid-search-rrf.md
docs/adr/0006-kommo-crm.md
docs/DEVELOPER_GUIDE.md
docs/ADD_NEW_RAG_NODE.md
docs/API_REFERENCE.md
docs/HITL.md
docs/engineering/sdk-registry.md
docs/engineering/test-writing-guide.md
docs/engineering/issue-triage.md
telegram_bot/AGENTS.override.md
telegram_bot/README.md
services/README.md
mini_app/README.md
src/ingestion/unified/AGENTS.override.md
src/README.md
tests/README.md
scripts/README.md
```
