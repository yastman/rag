# File Structure Reorganization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up repository organizational debt — remove temp files, archive legacy content, move misplaced files, without changing any business logic.

**Architecture:** Evolutionary (incremental, reversible moves/deletions). No import rewrites beyond renamed files. No business logic changes.

**Tech Stack:** Bash (file operations), git (tracking moves), pre-commit hooks.

---

## Phase 1: Root Cleanup

### Task 1: Delete tmp* directories and files at root

**Files affected:** ~60 items at root level

- [ ] **Step 1: Verify what will be deleted**

Run:
```bash
ls -la /home/user/projects/rag-fresh/ | grep -E "tmp\.|^d.*tmp\.|^d.*uv-.*\.lock|^-.*tmp[0-9]"
```
Expected: List of 17 `tmp.*/` dirs, 30+ `tmp*.json/csv` files, 14 `uv-*.lock` files.

- [ ] **Step 2: Delete tmp* directories**

Run:
```bash
cd /home/user/projects/rag-fresh && rm -rf tmp.*/
```
Expected: Directories removed.

- [ ] **Step 3: Delete tmp* files (json/csv)**

Run:
```bash
cd /home/user/projects/rag-fresh && rm -f tmp*.json tmp*.csv
```
Expected: 30+ temp files removed.

- [ ] **Step 4: Delete uv-*.lock fragments**

Run:
```bash
cd /home/user/projects/rag-fresh && rm -f uv-*.lock
```
Expected: 14 lock file fragments removed.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "chore: remove tmp* and uv-*.lock artifacts from root"
```

### Task 2: Move e2e_tester.session and .test_durations

**Files:**
- Move: `e2e_tester.session` (28KB Telethon session)
- Move: `.test_durations` (579KB pytest artifact)

- [ ] **Step 1: Create destination directories**

Run:
```bash
mkdir -p /home/user/projects/rag-fresh/tests/e2e/
mkdir -p /home/user/projects/rag-fresh/data/test_artifacts/
```

- [ ] **Step 2: Move e2e_tester.session**

Run:
```bash
mv /home/user/projects/rag-fresh/e2e_tester.session /home/user/projects/rag-fresh/tests/e2e/
```

- [ ] **Step 3: Move .test_durations**

Run:
```bash
mv /home/user/projects/rag-fresh/.test_durations /home/user/projects/rag-fresh/data/test_artifacts/
```

- [ ] **Step 4: Commit**

```bash
git add tests/e2e/e2e_tester.session data/test_artifacts/.test_durations && git commit -m "chore: move session and test artifacts to data/ and tests/"
```

### Task 3: Delete GitHub workflows disabled duplicates

**Files:**
- Delete: `.github/workflows.disabled/ci.yml`
- Delete: `.github/workflows.disabled/ci.yml.disabled`
- Delete: `.github/workflows.disabled/nightly-heavy.yml`

- [ ] **Step 1: Verify files exist**

Run:
```bash
ls /home/user/projects/rag-fresh/.github/workflows.disabled/
```
Expected: `ci.yml`, `ci.yml.disabled`, `nightly-heavy.yml` among others.

- [ ] **Step 2: Delete the duplicate workflow files**

Run:
```bash
rm /home/user/projects/rag-fresh/.github/workflows.disabled/ci.yml \
   /home/user/projects/rag-fresh/.github/workflows.disabled/ci.yml.disabled \
   /home/user/projects/rag-fresh/.github/workflows.disabled/nightly-heavy.yml
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows.disabled/ && git commit -m "chore: remove duplicate disabled GitHub workflow files"
```

---

## Phase 2: Documentation Relocation

### Task 4: Move AGENTS.override.md to .claude/rules/features/

**Files:**
- Move: `src/ingestion/unified/AGENTS.override.md` → `.claude/rules/features/ingestion-unified.md`

- [ ] **Step 1: Create destination directory**

Run:
```bash
mkdir -p /home/user/projects/rag-fresh/.claude/rules/features/
```

- [ ] **Step 2: Move and rename file**

Run:
```bash
mv /home/user/projects/rag-fresh/src/ingestion/unified/AGENTS.override.md \
   /home/user/projects/rag-fresh/.claude/rules/features/ingestion-unified.md
```

- [ ] **Step 3: Commit**

```bash
git add .claude/rules/features/ingestion-unified.md && \
git commit -m "chore: move AGENTS.override.md to .claude/rules/features/"
```

### Task 5: Archive docs/plans/ and docs/reports/

**Files:**
- Create: `docs/archive/plans/plans-2026-03/` — move all 17 files from `docs/plans/`
- Create: `docs/archive/reports/reports-2026-02/` and `docs/archive/reports/reports-2026-03/` — move all 20 files from `docs/reports/`
- Create: `docs/archive/README.md` — rotation policy

- [ ] **Step 1: Create archive directories**

Run:
```bash
mkdir -p /home/user/projects/rag-fresh/docs/archive/plans/plans-2026-03/
mkdir -p /home/user/projects/rag-fresh/docs/archive/reports/reports-2026-02/
mkdir -p /home/user/projects/rag-fresh/docs/archive/reports/reports-2026-03/
```

- [ ] **Step 2: Move docs/plans/ files**

Run:
```bash
mv /home/user/projects/rag-fresh/docs/plans/* /home/user/projects/rag-fresh/docs/archive/plans/plans-2026-03/
```

- [ ] **Step 3: Move docs/reports/ files (split by date)**

Run:
```bash
# Move Feb 2026 files
mv /home/user/projects/rag-fresh/docs/reports/2026-02* /home/user/projects/rag-fresh/docs/archive/reports/reports-2026-02/
# Move Mar 2026 files
mv /home/user/projects/rag-fresh/docs/reports/2026-03* /home/user/projects/rag-fresh/docs/archive/reports/reports-2026-03/
```

- [ ] **Step 4: Write docs/archive/README.md**

Write:
```markdown
# Archive

Archived planning documents and validation reports.

## Plans (`plans-2026-03/`)

Working documents from March 2026 development cycle. Superseded by completed PRs and ongoing work.

## Reports (`reports-2026-02/`, `reports-2026-03/`)

Validation reports and SDK audit artifacts. JSON files are CI artifacts; MD files are human-readable summaries.

## Rotation Policy

Archive plans/reports older than 30 days after related work is completed and merged.
Do not commit new plans or reports here — they belong in `docs/plans/` or `docs/reports/` until archived.
```

- [ ] **Step 5: Commit**

```bash
git add docs/archive/ && git commit -m "chore: archive plans and reports from Feb-Mar 2026"
```

### Task 6: Delete docs/documents/ .docx

**Files:**
- Delete: `docs/documents/Кримінальний кодекс України - Кодекс України № 2341-III від 05.04.2001 - d82054-20250717.docx`

- [ ] **Step 1: Verify no references to this file**

Run:
```bash
grep -r "Кримінальний\|Кримінальний кодекс" /home/user/projects/rag-fresh/docs/ --include="*.md"
```
Expected: No matches (this is test data, not documentation).

- [ ] **Step 2: Delete the file and empty directory**

Run:
```bash
rm "/home/user/projects/rag-fresh/docs/documents/Кримінальний кодекс України - Кодекс України № 2341-III від 05.04.2001 - d82054-20250717.docx"
rmdir /home/user/projects/rag-fresh/docs/documents/
```

- [ ] **Step 3: Commit**

```bash
git add docs/ && git commit -m "chore: remove test data (Ukrainian Criminal Code docx) from docs/documents/"
```

---

## Phase 3: Source Tree Cleanup

### Task 7: Move Dockerfiles to docker/ and update compose.yml

**Files:**
- Move: `src/api/Dockerfile` → `docker/api/`
- Move: `src/voice/Dockerfile` → `docker/voice/`
- Move: `Dockerfile.ingestion` → `docker/ingestion/`
- Modify: `compose.yml` (3 references)

- [ ] **Step 1: Create destination directories**

Run:
```bash
mkdir -p /home/user/projects/rag-fresh/docker/api/
mkdir -p /home/user/projects/rag-fresh/docker/voice/
mkdir -p /home/user/projects/rag-fresh/docker/ingestion/
```

- [ ] **Step 2: Move Dockerfiles**

Run:
```bash
mv /home/user/projects/rag-fresh/src/api/Dockerfile /home/user/projects/rag-fresh/docker/api/
mv /home/user/projects/rag-fresh/src/voice/Dockerfile /home/user/projects/rag-fresh/docker/voice/
mv /home/user/projects/rag-fresh/Dockerfile.ingestion /home/user/projects/rag-fresh/docker/ingestion/
```

- [ ] **Step 3: Update compose.yml — Dockerfile.ingestion reference**

Read line ~XXX (ingestion service) and change:
```
dockerfile: Dockerfile.ingestion
```
to:
```
dockerfile: docker/ingestion/Dockerfile.ingestion
```

- [ ] **Step 4: Update compose.yml — src/api/Dockerfile reference**

Change:
```
dockerfile: src/api/Dockerfile
```
to:
```
dockerfile: docker/api/Dockerfile
```

- [ ] **Step 5: Update compose.yml — src/voice/Dockerfile reference**

Change:
```
dockerfile: src/voice/Dockerfile
```
to:
```
dockerfile: docker/voice/Dockerfile
```

- [ ] **Step 6: Verify compose.yml still valid**

Run:
```bash
cd /home/user/projects/rag-fresh && docker compose config --quiet
```
Expected: No output (valid YAML).

- [ ] **Step 7: Commit**

```bash
git add docker/api/Dockerfile docker/voice/Dockerfile docker/ingestion/Dockerfile.ingestion compose.yml
git add -u src/api/ src/voice/
git commit -m "chore: move Dockerfiles from src/ to docker/"
```

### Task 8: Rename duplicate search_engines.py files

**Files:**
- Rename: `src/evaluation/search_engines.py` → `src/evaluation/evaluation_search_engines.py`
- Rename: `src/retrieval/search_engines.py` → `src/retrieval/retrieval_search_engines.py`
- Modify: `src/evaluation/run_ab_test.py` (import update)
- Modify: `src/evaluation/search_engines_rerank.py` (import update)
- Modify: `src/evaluation/smoke_test.py` (import update)
- Modify: `src/retrieval/__init__.py` (import update)

- [ ] **Step 1: Rename evaluation search_engines**

Run:
```bash
mv /home/user/projects/rag-fresh/src/evaluation/search_engines.py \
   /home/user/projects/rag-fresh/src/evaluation/evaluation_search_engines.py
```

- [ ] **Step 2: Rename retrieval search_engines**

Run:
```bash
mv /home/user/projects/rag-fresh/src/retrieval/search_engines.py \
   /home/user/projects/rag-fresh/src/retrieval/retrieval_search_engines.py
```

- [ ] **Step 3: Update import in src/evaluation/run_ab_test.py**

Find line:
```python
from src.evaluation.search_engines import create_search_engine
```
Change to:
```python
from src.evaluation.evaluation_search_engines import create_search_engine
```

- [ ] **Step 4: Update import in src/evaluation/search_engines_rerank.py**

Find line:
```python
from src.evaluation.search_engines import BaselineSearchEngine
```
Change to:
```python
from src.evaluation.evaluation_search_engines import BaselineSearchEngine
```

- [ ] **Step 5: Update import in src/evaluation/smoke_test.py**

Find line:
```python
from search_engines import (
```
Change to:
```python
from evaluation_search_engines import (
```

- [ ] **Step 6: Update import in src/retrieval/__init__.py**

Read the file and update `from .search_engines import` → `from .retrieval_search_engines import` (the symbol names stay the same, only the module name changes).

- [ ] **Step 7: Verify imports work**

Run:
```bash
cd /home/user/projects/rag-fresh && uv run python -c "from src.evaluation.evaluation_search_engines import create_search_engine, BaselineSearchEngine; from src.retrieval.retrieval_search_engines import SearchEngine; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add src/evaluation/evaluation_search_engines.py src/retrieval/retrieval_search_engines.py
git add -u src/evaluation/run_ab_test.py src/evaluation/search_engines_rerank.py src/evaluation/smoke_test.py src/retrieval/__init__.py
git commit -m "chore: rename duplicate search_engines.py files"
```

### Task 9: Archive legacy ingestion files

**Files:**
- Create: `src/ingestion/legacy/` directory
- Create: `src/ingestion/legacy/README.md`
- Move: `src/ingestion/gdrive_flow.py` → `src/ingestion/legacy/`
- Move: `src/ingestion/gdrive_indexer.py` → `src/ingestion/legacy/`
- Move: `src/ingestion/service.py` → `src/ingestion/legacy/`

- [ ] **Step 1: Create legacy directory and README**

Run:
```bash
mkdir -p /home/user/projects/rag-fresh/src/ingestion/legacy/
```

Write `src/ingestion/legacy/README.md`:
```markdown
# Legacy Ingestion Files

These files are superseded by `src/ingestion/unified/`. Kept for reference only — do not use.

## Files

- `gdrive_flow.py` — Google Drive ingestion (deprecated)
- `gdrive_indexer.py` — Google Drive indexer (deprecated)
- `service.py` — Legacy ingestion service (deprecated)
```

- [ ] **Step 2: Move legacy files**

Run:
```bash
mv /home/user/projects/rag-fresh/src/ingestion/gdrive_flow.py \
   /home/user/projects/rag-fresh/src/ingestion/legacy/
mv /home/user/projects/rag-fresh/src/ingestion/gdrive_indexer.py \
   /home/user/projects/rag-fresh/src/ingestion/legacy/
mv /home/user/projects/rag-fresh/src/ingestion/service.py \
   /home/user/projects/rag-fresh/src/ingestion/legacy/
```

- [ ] **Step 3: Commit**

```bash
git add src/ingestion/legacy/
git add -u src/ingestion/
git commit -m "chore: archive legacy ingestion files to src/ingestion/legacy/"
```

### Task 10: Delete empty src/governance/

**Files:**
- Delete: `src/governance/` directory (empty — only README.md)

- [ ] **Step 1: Verify directory is empty of Python files**

Run:
```bash
ls /home/user/projects/rag-fresh/src/governance/
```
Expected: Only `README.md`.

- [ ] **Step 2: Delete the directory**

Run:
```bash
rm -rf /home/user/projects/rag-fresh/src/governance/
```

- [ ] **Step 3: Commit**

```bash
git add -u src/ && git commit -m "chore: remove empty src/governance/ directory"
```

---

## Phase 4: Scripts and Final Polish

### Task 11: Archive old scripts

**Files:**
- Create: `scripts/archive/` directory
- Move: One-off benchmark, experiment, and test scripts to `scripts/archive/`

**Scripts to archive** (one-off experiment scripts):
- `scripts/benchmark_acorn.py`
- `scripts/benchmark_llm.py`
- `scripts/check_image_drift.py`
- `scripts/export_traces_to_dataset.py`
- `scripts/generate_gold_set.py`
- `scripts/generate_test_properties.py`
- `scripts/index_contextual.py`
- `scripts/index_contextual_api.py`
- `scripts/index_local_docs.py`
- `scripts/index_services.py`
- `scripts/index_test_data.py`
- `scripts/index_test_properties.py`
- `scripts/index_test_properties_prod.py`
- `scripts/langfuse_alert.py`
- `scripts/langfuse_triage.py`
- `scripts/qdrant_ensure_indexes.py`
- `scripts/qdrant_snapshot.py`
- `scripts/reindex_to_binary.py`
- `scripts/run_experiment.py`
- `scripts/run_legal_grounding_audit.py`
- `scripts/setup_binary_collection.py`
- `scripts/setup_ingestion_collection.py`
- `scripts/setup_langfuse_dashboards.py`
- `scripts/setup_qdrant_collection.py`
- `scripts/setup_scalar_collection.py`
- `scripts/setup_score_configs.py`
- `scripts/test_contextualized_ab.py`
- `scripts/test_int8_vs_binary.py`
- `scripts/test_quantization_ab.py`
- `scripts/test_search_quality.py`
- `scripts/tmux_orch_identity.py`
- `scripts/update_advisor_prompts.py`
- `scripts/validate_queries.py`
- `scripts/validate_traces.py`
- `scripts/ground_truth_queries.json` (data file, not script)

**Keep** (actively used):
- `scripts/deploy-vps.sh`
- `scripts/docker-cleanup.sh`
- `scripts/git_hygiene.py`
- `scripts/kommo_seed.py`
- `scripts/monitor-workers.sh`
- `scripts/no-commit-to-main.sh`
- `scripts/qdrant_backup.sh`
- `scripts/qdrant_restore.sh`
- `scripts/smoke-zoo.sh`
- `scripts/test_bot_health.sh`
- `scripts/test_release_health_vps.sh`
- `scripts/validate_prod_env.sh`
- `scripts/__init__.py`
- `scripts/e2e/` (dir)
- `scripts/apartments/` (dir)
- `scripts/eval/` (dir)

- [ ] **Step 1: Create scripts/archive/ directory**

Run:
```bash
mkdir -p /home/user/projects/rag-fresh/scripts/archive/
```

- [ ] **Step 2: Move archived scripts**

Run:
```bash
cd /home/user/projects/rag-fresh
mv scripts/benchmark_acorn.py scripts/benchmark_llm.py scripts/check_image_drift.py scripts/archive/
mv scripts/export_traces_to_dataset.py scripts/generate_gold_set.py scripts/generate_test_properties.py scripts/archive/
mv scripts/index_contextual.py scripts/index_contextual_api.py scripts/index_local_docs.py scripts/archive/
mv scripts/index_services.py scripts/index_test_data.py scripts/index_test_properties.py scripts/archive/
mv scripts/index_test_properties_prod.py scripts/langfuse_alert.py scripts/langfuse_triage.py scripts/archive/
mv scripts/qdrant_ensure_indexes.py scripts/qdrant_snapshot.py scripts/reindex_to_binary.py scripts/archive/
mv scripts/run_experiment.py scripts/run_legal_grounding_audit.py scripts/archive/
mv scripts/setup_binary_collection.py scripts/setup_ingestion_collection.py scripts/archive/
mv scripts/setup_langfuse_dashboards.py scripts/setup_qdrant_collection.py scripts/archive/
mv scripts/setup_scalar_collection.py scripts/setup_score_configs.py scripts/archive/
mv scripts/test_contextualized_ab.py scripts/test_int8_vs_binary.py scripts/archive/
mv scripts/test_quantization_ab.py scripts/test_search_quality.py scripts/archive/
mv scripts/tmux_orch_identity.py scripts/update_advisor_prompts.py scripts/archive/
mv scripts/validate_queries.py scripts/validate_traces.py scripts/archive/
mv scripts/ground_truth_queries.json scripts/archive/
```

- [ ] **Step 3: Commit**

```bash
git add scripts/archive/
git add -u scripts/
git commit -m "chore: archive one-off experiment scripts to scripts/archive/"
```

### Task 12: Delete empty settings.local.json

**Files:**
- Delete: `.claude/settings.local.json` (empty `{}`)

- [ ] **Step 1: Verify file is empty**

Run:
```bash
cat /home/user/projects/rag-fresh/.claude/settings.local.json
```
Expected: `{}`

- [ ] **Step 2: Delete the file**

Run:
```bash
rm /home/user/projects/rag-fresh/.claude/settings.local.json
```

- [ ] **Step 3: Commit**

```bash
git add -u .claude/ && git commit -m "chore: remove empty settings.local.json"
```

### Task 13: Update .gitignore

**Files:**
- Modify: `.gitignore` (add blocking rules for temp files at root)

- [ ] **Step 1: Read current .gitignore**

Run:
```bash
tail -20 /home/user/projects/rag-fresh/.gitignore
```

- [ ] **Step 2: Add blocking rules for root-level temp artifacts**

Add to end of `.gitignore`:
```gitignore
# Prevent temp files at root level
tmp*/
.lock
*.tmp
```

Note: `uv.lock` at root is intentional for uv projects and should NOT be in .gitignore. The pattern `uv-*.lock` already exists in .gitignore to block lock file fragments.

- [ ] **Step 3: Commit**

```bash
git add .gitignore && git commit -m "chore: add .gitignore rules to block temp files at root"
```

### Task 14: Update README.md

**Files:**
- Modify: `README.md` (add section about new structure if needed)

- [ ] **Step 1: Read current README**

Run:
```bash
head -50 /home/user/projects/rag-fresh/README.md
```

- [ ] **Step 2: Check if README mentions any of the changed paths**

If `README.md` references:
- `src/api/Dockerfile` → update to `docker/api/Dockerfile`
- `src/voice/Dockerfile` → update to `docker/voice/Dockerfile`
- `Dockerfile.ingestion` → update to `docker/ingestion/Dockerfile.ingestion`

Update any such references. Otherwise, no major rewrite needed.

- [ ] **Step 3: Commit**

```bash
git add README.md && git commit -m "docs: update README for new file locations"
```

### Task 15: Add pre-commit hook for temp files

**Files:**
- Modify: `.pre-commit-config.yaml` (add new hook)

- [ ] **Step 1: Read current pre-commit config**

Run:
```bash
cat /home/user/projects/rag-fresh/.pre-commit-config.yaml
```

- [ ] **Step 2: Add trailing-whitespace check already exists; add root-temp check**

Add a new hook entry (if not already present) that blocks `tmp*` and `uv-*.lock` at root. Since `.gitignore` already blocks these, verify first. If already blocked by existing patterns, skip this step.

Run:
```bash
grep -E "tmp|uv-" /home/user/projects/rag-fresh/.gitignore
```
Expected: Should show existing patterns blocking these files.

If patterns exist in `.gitignore`, pre-commit doesn't need to duplicate them. If not, add to pre-commit.

- [ ] **Step 3: Commit** (only if changes were made)

```bash
git add .pre-commit-config.yaml && git commit -m "chore: add pre-commit hook for temp file blocking"
```

---

## Verification

After all tasks, run:

```bash
# Verify root has no tmp* or uv-*.lock
ls /home/user/projects/rag-fresh/ | grep -E "^tmp|^uv-" && echo "FAIL: temp files remain" || echo "PASS: root clean"

# Verify Dockerfiles moved
ls /home/user/projects/rag-fresh/docker/api/Dockerfile
ls /home/user/projects/rag-fresh/docker/voice/Dockerfile
ls /home/user/projects/rag-fresh/docker/ingestion/Dockerfile.ingestion

# Verify compose still works
docker compose config --quiet && echo "PASS: compose valid"

# Verify imports still work
uv run python -c "from src.evaluation.evaluation_search_engines import *; from src.retrieval.retrieval_search_engines import *; print('PASS: imports')"
```
