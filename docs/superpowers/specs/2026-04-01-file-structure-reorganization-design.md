# File Structure Reorganization Design

**Date:** 2026-04-01
**Type:** Project organization
**Scope:** Full repository — root, src/, docs/, scripts/, .claude/
**Approach:** Evolutionary (incremental fixes, no rewrites)

---

## 1. Context

The rag-fresh repository has accumulated organizational debt across multiple areas:

- **Root clutter:** 17 `tmp.*/` dirs, 30+ `tmp*.json/csv` files, 14 `uv-*.lock` files, Telethon session files
- **Misplaced source files:** Dockerfiles in `src/api/` and `src/voice/`, AGENTS.override.md in `src/ingestion/unified/`
- **Misplaced data files:** Ukrainian Criminal Code .docx in `docs/documents/`
- **Orphaned content:** Empty `src/governance/` directory, legacy `src/ingestion/gdrive_*.py` not archived
- **Duplicate code:** `search_engines.py` in both `src/evaluation/` and `src/retrieval/`
- **Unbounded archives:** 17 plans and 20 validation reports in `docs/plans/` and `docs/reports/` — no rotation
- **Overpopulated scripts:** 50+ scripts in `scripts/`, many are one-off utilities
- **Multiple CI copies:** 3 versions of ci.yml in `.github/workflows/`
- **Unclear purpose dirs:** `.codex/` (67MB grepai index), `.signals/` (38+ worker JSONs at root)

No functional changes. No import rewrites. No refactoring of business logic.

---

## 2. Design

### 2.1 Root Cleanup

| Action | Details |
|--------|---------|
| Delete `tmp.*/` directories | 17 dirs matching `tmp.*` pattern at root |
| Delete `tmp*.json`, `tmp*.csv` | 30+ temp files at root |
| Delete `uv-*.lock` files | 14 lock file fragments at root |
| Move `e2e_tester.session` | → `tests/e2e/` (create if not exists) |
| Move `.test_durations` | → `data/test_artifacts/` (create dir) |
| Add `.signals/` to `.gitignore` | Already gitignored but should not exist at root |
| Leave `uv.lock` | Standard uv lockfile at root — correct location |

**Pattern for future:** All temp artifacts go to `tmp/` or `data/` subdirs. Enforce via pre-commit hook.

### 2.2 Dockerfiles Relocation

| File | Move to |
|-------|---------|
| `src/api/Dockerfile` | `docker/api/` |
| `src/voice/Dockerfile` | `docker/voice/` |
| `Dockerfile.ingestion` (root) | `docker/ingestion/` |

**Update:** `compose.yml` references to these Dockerfiles must be updated.

### 2.3 Documentation in Source Tree

| File | Move to |
|-------|---------|
| `src/ingestion/unified/AGENTS.override.md` | `.claude/rules/features/` |

Rename to `ingestion-unified.md` to avoid collision with existing rules.

### 2.4 Empty / Legacy Source Cleanup

| Directory | Action |
|-----------|--------|
| `src/governance/` | Delete entire directory (empty, no code) |
| `src/ingestion/gdrive_flow.py` | → `src/ingestion/legacy/gdrive_flow.py` (create `legacy/` subdir) |
| `src/ingestion/gdrive_indexer.py` | → `src/ingestion/legacy/gdrive_indexer.py` |
| `src/ingestion/service.py` | → `src/ingestion/legacy/service.py` (also marked legacy in ruff ignore) |

Create `src/ingestion/legacy/README.md` explaining these are superseded by `src/ingestion/unified/`.

### 2.5 Duplicate Search Engines File

| File | Rename to |
|-------|-----------|
| `src/evaluation/search_engines.py` | `src/evaluation/evaluation_search_engines.py` |
| `src/retrieval/search_engines.py` | `src/retrieval/retrieval_search_engines.py` |

Update imports in affected files.

### 2.6 Docs Misplaced Data

| File | Action |
|------|--------|
| `docs/documents/Кримінальний кодекс...docx` | Delete (test data — confirm no references first) |

Verify no docs reference this file before deletion.

### 2.7 Archive Unbounded Directories

**`docs/plans/`** (17 files, all Mar 2026):
```
docs/archive/plans/
├── plans-2026-03/
│   ├── 2026-03-02-sdk-migration-audit.md
│   ├── 2026-03-13-issue-728-sdk-realignment-plan.md
│   └── ... (all 17 files)
```

**`docs/reports/`** (20 files, Feb-Mar 2026):
```
docs/archive/reports/
├── reports-2026-02/
│   └── ... (10 validation pairs + SDK audit)
├── reports-2026-03/
│   └── ... (remaining reports)
```

Create `docs/archive/README.md` explaining archive purpose and rotation policy.

### 2.8 SDK Migration Docs Consolidation

| File | Action |
|------|--------|
| `docs/SDK_MIGRATION_AUDIT_2026-03-13.md` | Keep (canonical) |
| `docs/SDK_MIGRATION_ROADMAP_2026-03-13.md` | Keep (canonical) |
| `docs/SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md` | Keep (canonical) |
| `docs/plans/2026-03-02-sdk-migration-audit.md` | Move to `docs/archive/plans/` |
| `docs/reports/2026-03-13-sdk-audit-plan-review.md` | Move to `docs/archive/reports/` |

**No consolidation.** The 3 root-level files are distinct (audit, roadmap, remediation report) and serve different purposes. Archive the plan/report variants.

### 2.9 Scripts Cleanup

| Action | Details |
|--------|---------|
| Create `scripts/archive/` | Move one-off scripts that haven't been used recently |
| Identify one-off scripts | `benchmark_*.py`, `run_experiment.py`, `test_*.py` scripts used once for specific tasks |
| Criteria for archiving | Scripts without a corresponding Makefile target or not run in last 30 days |

Move to `scripts/archive/` if unsure. Do not delete.

**Keep in root scripts/:**
- `deploy-vps.sh`
- `docker-cleanup.sh`
- `qdrant_backup.sh`, `qdrant_restore.sh`
- `validate_prod_env.sh`
- `kommo_seed.py` (referenced in docs)
- `git_hygiene.py` (project maintenance)

### 2.10 GitHub Workflows Cleanup

| File | Action |
|------|--------|
| `.github/workflows.disabled/ci.yml` | Delete (duplicate of active) |
| `.github/workflows.disabled/ci.yml.disabled` | Delete |
| `.github/workflows.disabled/nightly-heavy.yml` | Delete (duplicate of active) |

Keep only active workflow files.

### 2.11 .codex/ Directory

- Leave as-is — external tool state
- Add to `.gitignore` if not already (appears to be gitignored)

### 2.12 .claude/ Settings

| File | Action |
|------|--------|
| `settings.local.json` | Delete (empty `{}`) |

### 2.13 README Update

Update `README.md` to reflect new structure where applicable. No major rewrites.

### 2.14 Pre-commit Hook

Add a pre-commit hook to prevent future accumulation:
- Block `tmp.*` dirs at root
- Block `uv-*.lock` files at root
- Block files in `src/` that are not `.py` (except `Dockerfile` in docker/)

---

## 3. Execution Order

```
Phase 1: Root cleanup (safe, reversible)
  1.1 Delete tmp* and uv-*.lock
  1.2 Move e2e_tester.session and .test_durations
  1.3 Delete .github/workflows.disabled/ duplicates

Phase 2: Documentation relocation (safe, reversible)
  2.1 Move AGENTS.override.md
  2.2 Create docs/archive/ with plans and reports
  2.3 Delete docs/documents/ .docx

Phase 3: Source tree cleanup (requires import updates)
  3.1 Move Dockerfiles to docker/
  3.2 Update compose.yml references
  3.3 Rename duplicate search_engines.py
  3.4 Update imports
  3.5 Archive legacy ingestion files

Phase 4: Scripts and final polish
  4.1 Archive old scripts
  4.2 Delete empty governance/
  4.3 Update .gitignore
  4.4 Update README
  4.5 Add pre-commit hook for temp files
```

---

## 4. Out of Scope

- Import rewrites beyond renamed files
- Business logic refactoring
- Changing `src/` top-level structure (feature dirs are logical)
- Deleting active scripts
- Modifying `.codex/`
- Renaming `src/ingestion/unified/` or other nested modules
- Creating new features or changing functionality
