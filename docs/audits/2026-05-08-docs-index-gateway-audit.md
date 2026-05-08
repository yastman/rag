# Documentation Index and Gateway Audit — 2026-05-08

**Scope:** `AGENTS.md`, root `README.md`, `docs/README.md`, `docs/runbooks/README.md`, existence and shape of `docs/indexes/`, fast-lookup paths for common agent prompts.
**Method:** Direct file reads, `find`, `rg`, `make docs-check`, `git diff --check`, link-existence verification against `origin/dev`.
**Base:** `origin/dev`

---

## 1. Executive Summary

The documentation gateway and index layer is **healthy and current** on `origin/dev`. The `docs/indexes/` directory exists with the expected shape (4 files), all gateway docs correctly cross-reference it, and the fast-lookup paths for the audited prompts are complete. `make docs-check` passes with no broken relative links.

One minor discoverability gap exists: several `docs/` subdirectories referenced in `docs/README.md` lack index `README.md` files. This is outside the core gateway/index scope but worth noting for a future docs-hygiene pass.

**Risk level:** LOW.

---

## 2. Commands Run

```bash
find docs -maxdepth 2 -type d | sort
rg -n "docs/indexes|runbooks|traces|Qdrant|Redis|LiteLLM|Docker|fast|lookup|search" AGENTS.md README.md docs/README.md docs/runbooks/README.md docs
make docs-check
git diff --check
git fetch origin dev
git diff origin/dev -- docs/indexes/ docs/runbooks/README.md docs/README.md AGENTS.md
# Link-target existence checks for every file referenced in indexes/
```

All commands completed without errors. `make docs-check` reported "All relative Markdown links OK." `git diff --check` was clean.

---

## 3. Findings

### 3.1 `docs/indexes/` exists and matches expected shape — CONFIRMED

**Evidence:**
```
docs/indexes/
docs/indexes/README.md
docs/indexes/fast-search.md
docs/indexes/runtime-services.md
docs/indexes/observability-and-storage.md
```

- `README.md` provides a task-oriented table mapping use cases to the three index pages, plus a canonical-doc-owners table.
- `fast-search.md` provides `rg` recipes and `cat` commands for the prompts audited below.
- `runtime-services.md` orients to Docker services, ingestion, mini app, bot, and voice.
- `observability-and-storage.md` orients to Langfuse, Qdrant, Redis/cache, LiteLLM, and Postgres.

**Impact:** The known-drift hypothesis ("this directory may be missing on current origin/dev") is **not confirmed**. The index layer is present and functional.

**Canonical owner:** `docs/indexes/` (maintained by docs-hygiene workers).

**Proposed fix:** None required. Continue to treat `docs/indexes/` as the canonical goal-oriented entrypoint.

**Priority:** — (not a bug).

---

### 3.2 Gateway docs correctly route to `docs/indexes/`

**Evidence:**

| Gateway doc | Reference to indexes | Link target valid? |
|---|---|---|
| `AGENTS.md:66` | `start from [docs/indexes/](docs/indexes/)` | Yes → `docs/indexes/README.md` |
| `docs/README.md:7` | `see [indexes/](indexes/)` | Yes → `docs/indexes/README.md` |
| `docs/indexes/README.md:5` | Back-links to `../README.md` and `../runbooks/README.md` | Yes |

**Impact:** Agents and humans have a consistent, bidirectional navigation path between gateway docs and task-oriented indexes.

**Canonical owner:** `AGENTS.md` (agent行为规范); `docs/README.md` (human docs navigation).

**Proposed fix:** None required.

**Priority:** — (not a bug).

---

### 3.3 Fast-lookup paths for audited prompts are complete

**Evidence:**

| Prompt | Index page | Runbook / canonical doc | Coverage |
|---|---|---|---|
| "изучи последние трейсы" | `fast-search.md:7–19` | `docs/runbooks/LANGFUSE_TRACING_GAPS.md` | Full |
| "сломался Qdrant" | `fast-search.md:21–34` | `docs/runbooks/QDRANT_TROUBLESHOOTING.md`, `docs/QDRANT_STACK.md` | Full |
| "изучи Redis" | `fast-search.md:36–49` | `docs/runbooks/REDIS_CACHE_DEGRADATION.md`, `docs/TROUBLESHOOTING_CACHE.md` | Full |
| "Docker services" | `fast-search.md:51–64` | `DOCKER.md`, `services/README.md` | Full |

`docs/runbooks/README.md` also maps these exact operator requests to first commands and runbooks (`runbooks/README.md:9–12`).

**Impact:** No gap between agent instructions and actual docs.

**Canonical owner:** `docs/indexes/fast-search.md`; `docs/runbooks/README.md`.

**Proposed fix:** None required.

**Priority:** — (not a bug).

---

### 3.4 All runbooks and canonical docs referenced in indexes exist

**Evidence:** Existence checks for every path linked from `docs/indexes/*.md` and `docs/runbooks/README.md`:

- `docs/runbooks/LANGFUSE_TRACING_GAPS.md` — exists
- `docs/runbooks/QDRANT_TROUBLESHOOTING.md` — exists
- `docs/runbooks/REDIS_CACHE_DEGRADATION.md` — exists
- `docs/runbooks/LITEllm_FAILURE.md` — exists
- `docs/runbooks/POSTGRESQL_WAL_RECOVERY.md` — exists
- `docs/runbooks/vps-gdrive-ingestion-recovery.md` — exists
- `docs/TROUBLESHOOTING_CACHE.md` — exists
- `docs/QDRANT_STACK.md` — exists
- `docs/INGESTION.md` — exists
- `docs/GDRIVE_INGESTION.md` — exists
- `docs/RAG_QUALITY_SCORES.md` — exists
- `docs/LOCAL-DEVELOPMENT.md` — exists
- `DOCKER.md` — exists
- `services/README.md` — exists
- `mini_app/README.md` — exists
- `telegram_bot/README.md` — exists
- `docs/engineering/sdk-registry.md` — exists
- `docs/engineering/test-writing-guide.md` — exists
- `docs/engineering/issue-triage.md` — exists

**Impact:** Zero 404-equivalent broken links in the gateway/index layer.

**Canonical owner:** Individual doc owners.

**Proposed fix:** None required.

**Priority:** — (not a bug).

---

### 3.5 Missing index `README.md` files in `docs/` subdirectories — MINOR DISCOVERABILITY GAP

**Evidence:** Directories referenced or listed in `docs/README.md` without an index `README.md`:

| Path | Referenced in `docs/README.md`? | `README.md` present? |
|---|---|---|
| `docs/review/` | Yes (line 96) | **No** |
| `docs/portfolio/` | Yes (line 96) | **No** |
| `docs/plans/` | Yes (line 95) | **No** |
| `docs/engineering/` | Yes (line 93) | **No** |
| `docs/superpowers/` | No explicit link, but exists | **No** |
| `docs/superpowers/plans/` | No explicit link | **No** |
| `docs/superpowers/specs/` | No explicit link | **No** |

**Impact:** When an agent or human navigates to these directories, there is no immediate orientation page. They must browse file names or return to `docs/README.md`.

**Canonical owner:** Each subdirectory; `docs/README.md` for the listing.

**Proposed fix:** Add minimal `README.md` index files to `docs/review/`, `docs/portfolio/`, `docs/plans/`, `docs/engineering/`, and `docs/superpowers/` (and its subdirectories), following the folder-README contract (purpose, entrypoints, see-also links).

**Reserved files for future fix worker:**
- `docs/review/README.md`
- `docs/portfolio/README.md`
- `docs/plans/README.md`
- `docs/engineering/README.md`
- `docs/superpowers/README.md`
- `docs/superpowers/plans/README.md`
- `docs/superpowers/specs/README.md`

**Priority:** P2 (discoverability only; no broken functionality).

---

## 4. Verification Results

| Check | Command | Result |
|---|---|---|
| Docs link integrity | `make docs-check` | Passed |
| Git whitespace | `git diff --check` | Clean |
| Drift from `origin/dev` | `git diff origin/dev -- docs/indexes/ docs/runbooks/README.md docs/README.md AGENTS.md` | No diff |

---

## 5. Conclusion

The documentation gateway and index layer on `origin/dev` is **current, consistent, and functional**. The `docs/indexes/` directory is present with the expected 4-file shape, all gateway docs route to it correctly, and the fast-lookup paths for the audited operator prompts are complete. No P0 or P1 issues were found. The only finding is a set of missing subdirectory `README.md` indexes (P2), which is outside the core gateway scope and safe to defer.

**Next action:** None required for the gateway/index layer. A future docs-hygiene worker may address the missing subdirectory READMEs.
