# Engineering / Archive Documentation Audit — 2026-05-08

**Scope:** `docs/engineering/`, `docs/plans/`, `docs/superpowers/`, `docs/archive/`, `docs/audits/`, `docs/review/`, root-level SDK migration docs, and old plan/report artifacts.
**Branch:** `docs/docs-engineering-archive-audit-20260508` tracking `origin/dev`
**Method:** File inventory, `rg` keyword search, `make docs-check`, `git diff --check`, manual read of representative files.
**Related:** #1396 (docs maintenance), #728 (SDK migration), 2026-05-07 project-docs-order audit

---

## 1. Executive Summary

The engineering docs tree is **mostly healthy at the top level**, but **three categories of drift** create agent-orientation risk:

1. **Root-level historical SDK docs** (`docs/SDK_MIGRATION_*`, `docs/SDK_CANONICAL_*`) are superseded by plan files in `docs/plans/` and should be archived or bannered.
2. **`docs/plans/` contains 17 March 2026 files** that the 2026-04-01 file-structure-reorganization design explicitly directed into `docs/archive/plans/` — this move never happened.
3. **Three pre-existing doc bugs from the 2026-05-07 project-docs-order audit remain unfixed** (broken `.claude/rules/` links, mismatched `ADRS.md`, stale cache docs at root).

**Risk level:** MEDIUM. Agents reading `docs/` for canonical guidance may encounter duplicate, historical, or contradictory sources unless they know to prefer `docs/engineering/` and `docs/runbooks/` over root `docs/` and `docs/plans/`.

---

## 2. Doc Classification

### 2.1 Active Canonical (keep, maintain)

| Path | Purpose | Verdict |
|---|---|---|
| `docs/engineering/docs-maintenance.md` | Docs editing contract, lookup order, impact gate | **Active, current** — references correct Makefile targets and compose commands. |
| `docs/engineering/sdk-registry.md` | SDK/framework lookup, patterns, gotchas | **Active, current** — covers aiogram, aiogram-dialog, langgraph, qdrant-client, redisvl, langfuse, and others. |
| `docs/engineering/issue-triage.md` | Issue classification and routing | **Active, current** — aligned with `AGENTS.md`. |
| `docs/engineering/test-writing-guide.md` | Test placement, naming, markers | **Active, current** — references `pyproject.toml` markers and `make test-unit`. |
| `docs/engineering/swarm-context-budget.md` | Swarm orchestrator context rules | **Active, current** — defines DONE JSON shape and prompt-file handoff. |
| `docs/engineering/swarm-process-improvements.md` | CI/deploy process changes | **Active, current** — references real workflow files and test paths. |
| `docs/review/ACCESS_FOR_REVIEWERS.md` | Safe review commands and branch context | **Active, current** — correctly names `dev` as integration branch. |
| `docs/review/GITHUB_REPO_SETUP.md` | Repo metadata and branch hygiene | **Active, current** — consistent with `ACCESS_FOR_REVIEWERS.md`. |
| `docs/review/PROJECT_GUIDE.md` | Folder map and high-signal files | **Active, current** — lists real files and honest limitations. |
| `docs/audits/README.md` | Audit index | **Partially stale** — missing four 2026-05-07 audits (see §3.6). |
| `docs/archive/README.md` | Archive purpose statement | **Active, appropriate** — short and clear. |
| `docs/archive/workflows/README.md` | Disabled workflows explanation | **Active, appropriate** — lists real archived files. |

### 2.2 Current Audit / Report (dated evidence)

| Path | Date | Verdict |
|---|---|---|
| `docs/audits/2026-05-08-telethon-langfuse-runtime-loop.md` | 2026-05-08 | Current |
| `docs/audits/2026-05-07-project-docs-order-audit.md` | 2026-05-07 | Current |
| `docs/audits/2026-05-07-docker-langfuse-health-audit.md` | 2026-05-07 | Current |
| `docs/audits/2026-05-07-langfuse-real-env-otel-fix.md` | 2026-05-07 | Current |
| `docs/audits/2026-05-07-telegram-bot-logs-audit.md` | 2026-05-07 | Current |
| `docs/audits/2026-05-05-langfuse-recent-traces-structure-audit.md` | 2026-05-05 | Current |
| `docs/audits/2026-05-05-langfuse-telethon-trace-audit.md` | 2026-05-05 | Current |
| `docs/audits/2026-05-05-langfuse-trace-8d79036a-audit.md` | 2026-05-05 | Current |

### 2.3 Historical / Reference-Only (should be archived or bannered)

| Path | Why historical | Proposed action |
|---|---|---|
| `docs/SDK_MIGRATION_AUDIT_2026-03-13.md` | Refreshed in `docs/plans/2026-03-02-sdk-migration-audit.md` and superseded by remediation report | **Archive banner + link** to canonical plan/report |
| `docs/SDK_MIGRATION_ROADMAP_2026-03-13.md` | Same as above | **Archive banner + link** |
| `docs/SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md` | Execution complete; plan is `docs/plans/2026-03-15-sdk-canonical-remediation-plan.md` | **Archive banner + link** |
| `docs/engineering/dependency-upgrade-blockers-2026-04.md` | Single resolved item (langfuse v4 migration done) | **Archive or delete** |
| `docs/plans/2026-03-02-sdk-migration-audit.md` | March 2026, superseded by realignment plan | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-13-issue-728-sdk-realignment-plan.md` | March 2026, execution completed | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-13-sdk-first-remediation-plan.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-15-sdk-canonical-remediation-plan.md` | March 2026, execution completed | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-16-open-issues-execution-design.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-16-pre-pr-pre-main-audit-report.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-17-vps-parity-audit-design.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-17-vps-parity-audit-report.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-17-vps-parity-fix-plan.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-18-grounded-rag-trace-retrieval-design.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-18-grounded-rag-trace-retrieval-implementation-plan.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-18-langfuse-local-to-vps-implementation-plan.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-19-catalog-dialog-migration-design.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-19-catalog-dialog-migration-implementation-plan.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-19-catalog-reply-keyboard-navigation-design.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-19-sdk-native-client-root-navigation.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/plans/2026-03-25-semantic-cache-degraded-response-hardening-design.md` | March 2026 | **Move to `docs/archive/plans/plans-2026-03/`** |
| `docs/superpowers/specs/2026-03-25-exhaustive-list-rag-design.md` | March 2026 | **Keep in `superpowers/specs/`** — design spec, not execution plan; still referenced |

### 2.4 Stale / Conflicting (needs fix or archive)

| Path | Problem | Evidence |
|---|---|---|
| `docs/TROUBLESHOOTING_CACHE.md` | Root-level cache doc duplicates runbook | 2026-05-07 audit §3.2 recommended archive/merge into `docs/runbooks/REDIS_CACHE_DEGRADATION.md` |
| `docs/CACHE_DEGRADATION.md` | Root-level cache doc duplicates runbook | Same as above |
| `docs/ADRS.md` | Mismatched titles vs `docs/adr/000*.md` | 2026-05-07 audit §4.1 table shows zero matches |
| `docs/HITL.md:137` | Broken link to `.claude/rules/features/telegram-bot.md` | Target does not exist |
| `docs/API_REFERENCE.md:205` | Broken link to `.claude/rules/features/telegram-bot.md` | Target does not exist |
| `docs/BOT_INTERNAL_STRUCTURE.md:176` | Broken link to `.claude/rules/features/telegram-bot.md` | Target does not exist |
| `docs/ONBOARDING.md:171–172` | Broken link to `.claude/rules/troubleshooting.md` | Target does not exist |
| `docs/ONBOARDING.md:178` | Broken link to `.claude/rules/features/telegram-bot.md` | Target does not exist |

---

## 3. Detailed Findings

### 3.1 Root-level SDK migration docs are not archived

**Evidence:**
- `docs/SDK_MIGRATION_AUDIT_2026-03-13.md` (70 lines) duplicates the refreshed audit in `docs/plans/2026-03-02-sdk-migration-audit.md` (93 lines).
- `docs/SDK_MIGRATION_ROADMAP_2026-03-13.md` (39 lines) is a post-audit execution order that was superseded by the remediation plan.
- `docs/SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md` (116 lines) reports completed phases 0–8.

**Impact:** Agents searching `docs/` for SDK guidance may read the root-level summary instead of the more detailed plan files, or may read the completed remediation report as active work.

**Proposed fix:**
- Add an archive banner to each root file: `> **Historical — execution complete. See `docs/plans/2026-03-15-sdk-canonical-remediation-plan.md` for the canonical plan.**`
- OR move them to `docs/archive/sdk-migration/` and update `docs/README.md` links.
- **Priority:** LOW. **Affects agent orientation:** Yes (duplicate source of truth).

### 3.2 March 2026 plans were never moved to archive

**Evidence:**
- `docs/superpowers/specs/2026-04-01-file-structure-reorganization-design.md` §2.7 explicitly maps 17 March 2026 `docs/plans/` files → `docs/archive/plans/plans-2026-03/`.
- `ls docs/archive/plans/` returns **0 files**.
- `ls docs/plans/` still lists all 21 March–May files, including the 17 March files.

**Impact:** The `docs/plans/` directory is unbounded; agents cannot distinguish active plans from completed March work without reading each file.

**Proposed fix:**
- Move the 17 March 2026 files to `docs/archive/plans/plans-2026-03/`.
- Keep April–May 2026 files in `docs/plans/` (they are active or recent).
- Update `docs/archive/README.md` to mention the plans archive.
- **Priority:** MEDIUM. **Affects agent orientation:** Yes (cluttered index).

### 3.3 `docs/engineering/dependency-upgrade-blockers-2026-04.md` is resolved

**Evidence:**
- File contains exactly one bullet: "`langfuse`: blocker resolved by the native v4 migration."
- `docs/engineering/sdk-registry.md` and code already reflect `langfuse>=4.0.0`.

**Proposed fix:**
- Archive the file or delete it. If kept, add a banner noting resolution.
- **Priority:** LOW. **Affects agent orientation:** Minimal.

### 3.4 Cache docs triplicate persists

**Evidence:**
- `docs/TROUBLESHOOTING_CACHE.md` (188 lines) and `docs/CACHE_DEGRADATION.md` (93 lines) still exist at root `docs/`.
- `docs/runbooks/REDIS_CACHE_DEGRADATION.md` exists as the runbook format.
- 2026-05-07 audit §3.2 recommended merging or archiving them.

**Proposed fix:**
- Move both files to `docs/archive/` or merge their unique content into `docs/runbooks/REDIS_CACHE_DEGRADATION.md`, then delete the root copies.
- **Priority:** LOW. **Affects agent orientation:** Yes (threshold drift risk).

### 3.5 Broken `.claude/rules/` links and ADR mismatch remain unfixed

**Evidence:**
- 2026-05-07 audit §5.3 listed five broken links; `rg -n "\.claude/" docs/` still finds them.
- 2026-05-07 audit §4.1 showed `docs/ADRS.md` titles do not match `docs/adr/000*.md` files.

**Proposed fix:**
- Fix or remove the five broken links (replace with nearest folder README or AGENTS.override.md).
- Convert `docs/ADRS.md` to a lightweight index linking to `docs/adr/`, or archive it.
- **Priority:** MEDIUM. **Affects agent orientation:** Yes (broken links waste time).

### 3.6 `docs/audits/README.md` is missing four 2026-05-07 audit entries

**Evidence:**
- `docs/audits/README.md` lists 7 audits, all dated 2026-05-05 and 2026-05-08.
- Four 2026-05-07 audits exist in the directory but are omitted:
  - `2026-05-07-docker-langfuse-health-audit.md`
  - `2026-05-07-langfuse-real-env-otel-fix.md`
  - `2026-05-07-telegram-bot-logs-audit.md`
  - `2026-05-07-project-docs-order-audit.md`

**Proposed fix:**
- Add the four missing entries to `docs/audits/README.md` under a "2026-05-07" subsection.
- **Priority:** LOW. **Affects agent orientation:** Yes (incomplete index).

### 3.7 `docs/superpowers/` plans and specs are current but unbounded

**Evidence:**
- `docs/superpowers/plans/` has 11 files (April–May 2026).
- `docs/superpowers/specs/` has 7 files (March–April 2026).
- No archive subdirectory exists for superpowers docs.

**Assessment:** These are design artifacts produced by the swarm process. They are not canonical operational docs, but they are recent enough to keep accessible. When they age past 60 days or their associated issues close, they should move to `docs/archive/superpowers/`.

**Proposed fix:**
- Add a note to `docs/superpowers/` README (if one exists) or to `docs/archive/README.md` stating the 60-day rotation policy.
- **Priority:** LOW. **Affects agent orientation:** No (agents should not treat superpowers docs as canonical).

---

## 4. Verification Commands Run

```bash
# File inventory
rg --files docs/engineering docs/plans docs/superpowers docs/archive docs/audits docs/review | sort

# Keyword scan
rg -n "main|dev|docs/indexes|CLAUDE|AGENTS|make check|test-unit|SDK|deprecated|archive|2026-03|2026-04|2026-05" docs/engineering docs/plans docs/superpowers docs/archive docs/audits docs/review

# Docs link check
make docs-check
# exit 0 — All relative Markdown links OK.

# Git diff check
git diff --check
# exit 0 — no trailing whitespace or conflict markers
```

---

## 5. Recommendations Summary

| # | Action | Files / worker | Priority | Affects agents? |
|---|---|---|---|---|
| 1 | Archive-banner or move root-level SDK migration docs | `docs/SDK_MIGRATION_AUDIT_2026-03-13.md`, `docs/SDK_MIGRATION_ROADMAP_2026-03-13.md`, `docs/SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md` | LOW | Yes |
| 2 | Move 17 March 2026 plan files to `docs/archive/plans/plans-2026-03/` | `docs/plans/2026-03-*.md` | MEDIUM | Yes |
| 3 | Delete or archive resolved dependency blockers file | `docs/engineering/dependency-upgrade-blockers-2026-04.md` | LOW | No |
| 4 | Consolidate or archive root cache docs | `docs/TROUBLESHOOTING_CACHE.md`, `docs/CACHE_DEGRADATION.md` | LOW | Yes |
| 5 | Fix broken `.claude/rules/` links and ADR mismatch | `docs/HITL.md`, `docs/API_REFERENCE.md`, `docs/BOT_INTERNAL_STRUCTURE.md`, `docs/ONBOARDING.md`, `docs/ADRS.md` | MEDIUM | Yes |
| 6 | Add missing 2026-05-07 audits to index | `docs/audits/README.md` | LOW | Yes |
| 7 | Document superpowers doc rotation policy | `docs/archive/README.md` or new `docs/superpowers/README.md` | LOW | No |

---

*Audit generated by `W-docs-engineering-archive-audit-20260508` on 2026-05-08.*
