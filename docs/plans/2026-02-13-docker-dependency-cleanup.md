# Docker Dependency Cleanup — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove dead Docker services, safely slim Python dependencies, and split deps into optional groups to reduce image sizes without breaking runtime paths.

**Architecture:** Root `pyproject.toml` currently bundles evaluation, ingestion, and ML packages together. Split into `[project.optional-dependencies.eval]` and `[project.optional-dependencies.ingest]` groups so API/voice images don't install unnecessary deps. Remove dead services (bm42, lightrag). Remove packages only after import-audit gates (`rg`) confirm they are unused in active code paths.

**Tech Stack:** uv, Docker, pyproject.toml (PEP 621), docker-compose profiles

**Issue:** #246

---

## SDK Baseline (validated 2026-02-13)

- `uv` does not install extras by default; use `uv sync --extra <group>` for targeted installs.
- For Docker + `uv`, keep two-stage sync for cache efficiency: deps first (`--no-install-project`), then project sync.
- Docker Compose profiles should keep core services unprofiled and toggle optional services via `--profile`.
- Compose changes should be validated with `docker compose config --quiet`; optionally add `docker compose --dry-run` for safe command rehearsal.

---

## Phase 1: Quick Cleanup (dead code removal)

### Task 1: Remove dead packages from `telegram_bot/pyproject.toml`

**Files:**
- Modify: `telegram_bot/pyproject.toml`

**Step 1: Remove unused packages**

Remove these 2 packages (zero imports in telegram_bot/):
- `fastembed>=0.4.0` — BM42 service has own pyproject, never imported in bot
- `langchain-text-splitters>=1.0.0` — never imported anywhere in codebase

NOTE: Keep `langchain-openai>=0.3.0` — used in `telegram_bot/graph/graph.py:236` by `SummarizationNode`.

**Step 2: Regenerate lockfile**

Run: `cd /home/user/projects/rag-fresh/telegram_bot && uv lock`
Expected: lockfile updated, no errors

**Step 3: Verify bot still resolves**

Run: `cd /home/user/projects/rag-fresh/telegram_bot && uv sync --frozen --no-dev --dry-run`
Expected: no errors

**Step 4: Commit**

```bash
git add telegram_bot/pyproject.toml telegram_bot/uv.lock
git commit -m "chore(bot): remove unused fastembed, langchain-text-splitters deps

Part of #246"
```

---

### Task 2: Root package cleanup (safe subset only)

**Files:**
- Modify: `pyproject.toml`

**Step 1: Run import-audit gate before removal**

Check candidate removals with `rg` first, then apply only proven-safe deletions.

Current findings:
- `fastembed` is used in active ingestion modules (`src/ingestion/gdrive_indexer.py`, `src/ingestion/voyage_indexer.py`) and must not be removed in this task.
- `aiohttp` is used outside `legacy/` (e.g. `src/evaluation/generate_test_queries.py`, tests) and must not be removed in this task.
- `langchain-text-splitters` is not in root `pyproject.toml`, so there is nothing to remove at root for this package.

**Step 2: Regenerate lockfile**

Run: `cd /home/user/projects/rag-fresh && uv lock`
Expected: lockfile updated

**Step 3: Run linter + type checker**

Run: `cd /home/user/projects/rag-fresh && uv run ruff check . && uv run mypy telegram_bot/ src/ --ignore-missing-imports`
Expected: no new errors

**Step 4: Run unit tests**

Run: `cd /home/user/projects/rag-fresh && PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
Expected: all pass

**Step 5: Commit (only if files changed)**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): apply safe root dependency cleanup from import audit

Skip removals for active deps (fastembed/aiohttp), keep follow-up for deeper optionalization.

Part of #246"
```

---

### Task 3: Remove BM42 service directory

**Files:**
- Delete: `services/bm42/Dockerfile`
- Delete: `services/bm42/main.py`
- Modify: `Makefile` (update comment)

**Step 1: Delete BM42 service directory**

BM42 was already removed from docker-compose.dev.yml and docker-compose.vps.yml. Only `services/bm42/` directory remains as dead code.
Note: this does NOT imply `fastembed` can be removed from root yet; ingestion modules still use it.

```bash
rm -rf services/bm42/
```

**Step 2: Fix Makefile comment**

In `Makefile`, line 312:
```
# Before:
docker-core-up: ## Start core services (postgres, qdrant, redis, docling, bm42)
# After:
docker-core-up: ## Start core services (postgres, qdrant, redis, docling)
```

**Step 3: Commit**

```bash
git add -A services/bm42/ Makefile
git commit -m "chore(docker): remove dead BM42 service directory

BM42 sparse embeddings replaced by BGE-M3 /encode/sparse.
Already removed from docker-compose, this cleans up leftover files.

Part of #246"
```

---

### Task 4: Remove LightRAG from docker-compose

**Files:**
- Modify: `docker-compose.dev.yml`

**Step 1: Remove lightrag service block**

Remove the entire `lightrag:` service definition (lines 169-190) and `lightrag_data:` volume.

NOTE: Keep #234 open for future LightRAG integration — that will add it back properly.

**Step 2: Fix Makefile comment**

In `Makefile`, line 332:
```
# Before:
docker-ai-up: ## Start core + heavy AI services (bge-m3, user-base, lightrag)
# After:
docker-ai-up: ## Start core + heavy AI services (bge-m3, user-base)
```

**Step 3: Validate compose**

Run: `docker compose -f docker-compose.dev.yml config --quiet`
Expected: no errors

**Step 4: Commit**

```bash
git add docker-compose.dev.yml Makefile
git commit -m "chore(docker): remove lightrag service from compose

Zero Python imports — experimental only, tracked in #234 for future integration.
Removes lightrag service + lightrag_data volume.

Part of #246"
```

---

### Task 5: Remove duplicate root Dockerfile

**Files:**
- Delete: `Dockerfile`
- Modify: `docker-compose.dev.yml` (check no reference)

**Step 1: Verify no active reference to root Dockerfile**

Root `Dockerfile` and `telegram_bot/Dockerfile` are very close. Before deletion, verify there is no runtime/CI path that builds root `Dockerfile` with project root as build context.

Run:
- `rg -n 'dockerfile:\\s*Dockerfile$|context:\\s*\\.' docker-compose*.yml`
- `rg -n '\\bDockerfile\\b' .github Makefile scripts`

Expected:
- `dockerfile: Dockerfile` matches are allowed for service-local contexts (e.g. `./services/*`).
- There must be no active root-context build path that still targets root `Dockerfile`.

**Step 2: Delete root Dockerfile**

```bash
rm Dockerfile
```

**Step 3: Commit**

```bash
git rm Dockerfile
git commit -m "chore(docker): remove duplicate root Dockerfile

Identical to telegram_bot/Dockerfile. Bot service already uses
telegram_bot/Dockerfile in docker-compose.

Part of #246"
```

---

## Phase 2: Split Optional Dependencies

### Task 6: Create eval optional-dependencies group

**Files:**
- Modify: `pyproject.toml`

**Step 1: Move evaluation-only packages to `[project.optional-dependencies.eval]`**

Move these from `[project.dependencies]` to new `[project.optional-dependencies.eval]`:
- `mlflow>=3.9.0`
- `ragas>=0.4.3`
- `datasets>=3.0.0`
- `pandas>=2.0.0`

Add the group:
```toml
[project.optional-dependencies]
# Evaluation tools (RAGAS, MLflow, dataset generation)
eval = [
    "mlflow>=3.9.0",
    "ragas>=0.4.3",
    "datasets>=3.0.0",
    "pandas>=2.0.0",
]
```

Update `all` group:
```toml
all = [
    "contextual-rag[docs,voice,eval]",
]
```

**Step 2: Regenerate lockfile**

Run: `uv lock`

**Step 3: Verify eval still installs**

Run: `uv sync --extra eval --dry-run`
Expected: evaluation packages resolve

**Step 4: Run evaluation import check**

Run: `uv sync --extra eval && uv run python -c "import mlflow; import ragas; import datasets; print('OK')"`
Expected: OK

**Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): move evaluation packages to optional [eval] group

mlflow, ragas, datasets, pandas — evaluation-only stack, not needed in API/voice runtime.

Part of #246"
```

---

### Task 7: Create ingest optional-dependencies group (safe subset)

**Files:**
- Modify: `pyproject.toml`

**Step 1: Move ingestion-only packages to `[project.optional-dependencies.ingest]`**

Move from `[project.dependencies]` to new `[project.optional-dependencies.ingest]`:
- `pymupdf>=1.26.0`
- `docling>=2.70.0`
- `docling-core>=2.61.0`
- `cocoindex>=0.3.28`
- `fastembed>=0.7.4`

Add the group:
```toml
# Ingestion pipeline (Docling, CocoIndex, PyMuPDF)
ingest = [
    "pymupdf>=1.26.0",
    "docling>=2.70.0",
    "docling-core>=2.61.0",
    "cocoindex>=0.3.28",
    "fastembed>=0.7.4",
]
```

Keep in root for now (used in active runtime imports): `FlagEmbedding`, `sentence-transformers`, `torch`, `torchvision`, `scipy`, `transformers`.

Update `all` group:
```toml
all = [
    "contextual-rag[docs,voice,eval,ingest]",
]
```

**Step 2: Regenerate lockfile**

Run: `uv lock`

**Step 3: Verify ingestion installs**

Run: `uv sync --extra ingest --dry-run`
Expected: ingestion packages resolve

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore(deps): move ingestion packages to optional [ingest] group

pymupdf, docling, docling-core, cocoindex, fastembed —
used only by src/ingestion/, not needed in bot/API/voice images.

Part of #246"
```

---

### Task 8: Create follow-up for model-stack optionalization (not in this issue)

**Files:**
- Modify: `docs/plans/2026-02-13-docker-dependency-cleanup.md` (this plan)

**Step 1: Record blockers for immediate move**

Do not move these in #246 yet:
- `FlagEmbedding`, `sentence-transformers`, `torch`, `torchvision`, `scipy`, `transformers`

Reason:
- Active imports exist in runtime modules (`src/models/embedding_model.py`, `src/retrieval/reranker.py`) and test suites.
- Moving them without lazy-import refactor can break import-time behavior for API/voice/test environments.

**Step 2: Open follow-up issue**

Follow-up issue created: **#249** — `chore(deps): optionalize model-stack (torch/sentence-transformers) with lazy imports`

Track a dedicated follow-up issue to:
- add lazy imports / provider-gated imports,
- introduce `[project.optional-dependencies.ml-local]`,
- then move model stack safely with targeted tests.

**Step 3: Commit plan update**

```bash
git add docs/plans/2026-02-13-docker-dependency-cleanup.md
git commit -m "docs(plan): defer model-stack optionalization to follow-up issue

Avoid risky move of torch/sentence-transformers stack without lazy-import migration.

Part of #246"
```

---

### Task 9: Update Dockerfile.ingestion to use --extra ingest

**Files:**
- Modify: `Dockerfile.ingestion`

**Step 1: Update uv sync commands**

Change both `uv sync` lines:
```dockerfile
# Before:
RUN uv sync --frozen --no-dev --no-install-project
# ...
RUN uv sync --frozen --no-dev

# After:
RUN uv sync --locked --no-dev --extra ingest --no-install-project
# ...
RUN uv sync --locked --no-dev --extra ingest
```

**Step 2: Validate Dockerfile syntax**

Run: `docker compose -f docker-compose.dev.yml config --quiet`
Expected: no errors

**Step 3: Commit**

```bash
git add Dockerfile.ingestion
git commit -m "chore(docker): ingestion Dockerfile uses --extra ingest

Makes ingestion extra explicit in container build, so ingestion-only deps
remain installed after root/optional split.

Part of #246"
```

---

### Task 10: Move MLflow to eval profile in docker-compose

**Files:**
- Modify: `docker-compose.dev.yml`

**Step 1: Change MLflow profile**

```yaml
# Before:
  mlflow:
    ...
    profiles: ["ml", "full"]

# After:
  mlflow:
    ...
    profiles: ["eval", "ml", "full"]
```

**Step 2: Validate compose**

Run: `docker compose -f docker-compose.dev.yml config --quiet`
Expected: no errors

**Step 3: Commit**

```bash
git add docker-compose.dev.yml
git commit -m "chore(docker): add eval profile to mlflow service

MLflow used only for evaluation. Now accessible via --profile eval
alongside existing ml/full profiles.

Part of #246"
```

---

### Task 11: Update CLAUDE.md and docs references

**Files:**
- Modify: `CLAUDE.md` (update docker profiles table, remove bm42/lightrag refs)
- Modify: `.claude/rules/docker.md` (update container table, profiles)

**Step 1: Update CLAUDE.md**

- Remove bm42 from profile descriptions
- Remove lightrag from service counts
- Update service count: 19 → 17
- Add `eval` profile to profile table

**Step 2: Update docker.md rule**

- Remove `bm42` and `lightrag` from container table
- Update `docker-core-up` description
- Update `docker-ai-up` description
- Add `eval` profile

**Step 3: Commit**

```bash
git add CLAUDE.md .claude/rules/docker.md
git commit -m "docs: update Docker docs after dependency cleanup

Remove bm42/lightrag references, add eval profile, update service counts.

Part of #246"
```

---

### Task 12: Final verification

**Step 1: Check lock consistency + lint/types**

Run: `uv lock --check && make check`
Expected: pass

**Step 2: Run unit tests**

Run: `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
Expected: all pass

**Step 3: Verify Docker build (bot)**

Run in tmux:
```bash
docker compose -f docker-compose.dev.yml build bot 2>&1 | tee logs/build-bot.log
```
Expected: builds successfully

**Step 4: Close issue**

```bash
gh issue close 246 -c "Completed Phase 1 + Phase 2. See commits on feat/docker-cleanup branch."
```

---

## Summary

| Phase | Tasks | Packages removed | Services removed | Est. image saving |
|-------|-------|-----------------|-----------------|-------------------|
| 1 (cleanup) | 1-5 | bot deps cleanup + root safe-audit | bm42 dir, lightrag compose | small |
| 2 (split deps) | 6-12 | eval + ingest safe subset moved to optional extras | mlflow → eval profile | medium |
| **Total** | **12** | **risk-reduced slimming with follow-up for model stack** | **2 services removed** | **TBD after lock diff + image build** |
