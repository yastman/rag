# Documentation Actualization Audit — 2026-05-08 (codex321)

Scope:
- Full docs actualization status on branch `docs/codex321-docs-audit-20260508`.
- Cross-check with existing PR-audit PRs #1433-#1437 and current working tree.
- Focus on fast orientation paths for prompts like "изучи последние трейсы", Qdrant/Redis/Docker failures, and worker/PR docs usage.

## Executive Summary

1. `docs/indexes` is current and functional on this branch; no P0/P1 staleness found in gateway/index layer.
2. Current high-value drift is concentrated in docs-orientation and canonicalization, not in gateway/index mechanics.
3. At least two P1 items remain unaddressed (`k8s/AGENTS.override.md` contract mismatch and ADR mismatch), plus several P2 doc discoverability gaps.
4. `make docs-check` is passing on current branch, but CI currently does not enforce it.

## Cross-reference against existing PR-audit branches

- `#1433` (`docs/full-actualization-audit-20260508`): open at the time of this audit; later updated to include merged audit artifacts in `docs/audits/README.md`.
  - Adds `docs/audits/2026-05-08-full-docs-actualization-audit.md` for a superset of findings.
- `#1434` (`docs/docs-index-gateway-audit-20260508`): merged to `dev` after this audit was produced.
  - Confirmed finding: `docs/indexes/` exists and is current.
- `#1435` (`docs/docs-engineering-archive-audit-20260508`): merged to `dev` after review-fix.
  - Confirms recurring engineering/archive hygiene gaps in canonicalization and discoverability.
- `#1436` (`docs/docs-subsystem-readmes-audit-20260508`): merged to `dev` after review-fix.
  - Confirms lower-priority subsystem README discoverability gaps.
- `#1437` (`docs/docs-runtime-runbooks-audit-20260508`): merged to `dev` after review-fix.
  - Confirms runtime/runbook command drift against Compose contracts.

## Verification Commands Run (required)

- `make docs-check`
- `git diff --check`
- `rg -n "\\.claude/" docs README.md DOCKER.md AGENTS.md .github/workflows/ci.yml Makefile compose.yml compose.dev.yml`
- `rg -n "docs/indexes|runbooks|Fast Search|QDRANT|Redis|LiteLLM|observe|validate-traces-fast" AGENTS.md README.md docs/README.md docs/indexes docs/runbooks docs/engineering docs/audits README.md`
- `find docs -mindepth 2 -type d -name README.md` and directory scan for subdirs with markdown but no README
- `COMPOSE_DISABLE_ENV_FILE=1 docker compose --env-file tests/fixtures/compose.ci.env -f compose.yml -f compose.dev.yml config --services`

Results:
- `make docs-check` → All relative Markdown links OK.
- `git diff --check` → no whitespace/conflict issues.
- `.claude` path references remain in historical/superseded docs; no active runtime/help docs currently depend on them.
- `docs/indexes` and referenced gateway docs have valid links.
- Compose native config command returns base services: `user-base bge-m3 docling qdrant redis mini-app-api mini-app-frontend postgres`.

## Key Findings

### F1 — `docs/indexes` is current and healthy
- Evidence: branch 1434, local `make docs-check`, explicit file inventory, and `docs/README.md` / `AGENTS.md` linkage.
- Impact: low.
- Action: no immediate fix required.

### F2 — k8s override contract is declared but missing
- Evidence: `AGENTS.md` lists `k8s/AGENTS.override.md`; on-disk scan finds only:
  - `telegram_bot/AGENTS.override.md`
  - `src/ingestion/unified/AGENTS.override.md`
- Command-backed: `find . -maxdepth 4 -name AGENTS.override.md`.
- Impact: medium/high (workflow guidance can misroute workers to missing rule layer).
- Action: create `k8s/AGENTS.override.md` or remove the root reference.

### F3 — ADRs are split between canonical and stale surfaces
- Evidence: `docs/ADRS.md` holds full ADR text with outdated titles and older numbering narrative; `docs/adr/README.md` plus `docs/adr/0001-...` files represent the active ADR home.
- Evidence command: `sed -n` reads of both files.
- Impact: medium (wrong first-source-of-truth for architecture changes).
- Action: de-duplicate/redirect `docs/ADRS.md` to `docs/adr/README.md` or archive clearly.

### F4 — Onboarding env contract is stale vs canonical contract docs
- Evidence: `docs/ONBOARDING.md` still documents `LITELLM_API_KEY`, `LANGFUSE_HOST=https://cloud.langfuse.com`, and `BGE_M3_URL=http://localhost:8000`.
- Canonical check target: `docs/LOCAL-DEVELOPMENT.md` + `DOCKER.md` + `compose.yml`/`compose.dev.yml` + `Makefile`.
- Impact: medium (new contributors may bootstrap against incorrect env assumptions).
- Action: rewrite/checklist to reference canonical flow and current variable naming.

### F5 — CI does not run `make docs-check`
- Evidence: `rg` in `.github/workflows/ci.yml` shows no `docs-check` target invocation.
- Impact: medium (markdown drift may merge without CI guard).
- Action: add `make docs-check` in CI workflow.

### F6 — Folder-level README discoverability gaps remain (P2)
- Evidence from directory scan (directories with markdown content but no README):
  - `docs/engineering`
  - `docs/plans`
  - `docs/portfolio`
  - `docs/review`
  - `docs/superpowers/plans`
  - `docs/superpowers/specs`
- Impact: low/medium (navigation friction for worker/agent orientation).

### F7 — `docs/audits/README.md` is incomplete
- Evidence: at the time of this audit, the index missed an explicit link to `2026-05-07-project-docs-order-audit.md`.
- Command-backed check: script against `docs/audits/*.md` names.
- Impact: low (time-to-trace history regression).
- Disposition: covered by #1433, which updates `docs/audits/README.md`.

## Fix Wave Plan

Waves are disjoint by reserved files to support parallel execution.

### Wave 1 — Canonical onboarding + quick orientation updates (P1)
- Worker: `W-codex321-docs-onboarding-canonical`
- Reserved files:
  - `docs/ONBOARDING.md`
  - `docs/ONBOARDING_CHECKLIST.md`
  - `docs/LOCAL-DEVELOPMENT.md` (if used for redirects/links)
- Verification commands:
  - `rg -n "LITELLM_API_KEY|LANGFUSE_HOST|BGE_M3_URL" docs/ONBOARDING.md docs/ONBOARDING_CHECKLIST.md`
  - `make docs-check`
- Merge order: **1**

### Wave 2 — ADR canonicalization (P1)
- Worker: `W-codex321-docs-adr-contract`
- Reserved files:
  - `docs/ADRS.md`
  - `docs/adr/README.md`
- Verification commands:
  - `sed -n '1,220p' docs/ADRS.md`
  - `sed -n '1,200p' docs/adr/README.md`
  - `make docs-check`
- Merge order: **2**

### Wave 3 — Governance and CI guardrails (P1)
- Worker: `W-codex321-docs-governance`
- Reserved files:
  - `AGENTS.md`
  - `.github/workflows/ci.yml`
  - `k8s/AGENTS.override.md` (new file) or `AGENTS.md` (remove stale reference)
- Verification commands:
  - `find . -maxdepth 4 -name AGENTS.override.md`
  - `rg -n "docs-check" .github/workflows/ci.yml`
  - `make docs-check`
- Merge order: **3**

### Wave 4 — Discoverability scaffolding and audit ledger completeness (P2)
- Worker: `W-codex321-docs-index-scaffolding`
- Reserved files:
  - `docs/engineering/README.md`
  - `docs/plans/README.md`
  - `docs/portfolio/README.md`
  - `docs/review/README.md`
  - `docs/superpowers/README.md`
  - `docs/superpowers/plans/README.md`
  - `docs/superpowers/specs/README.md`
  - `docs/audits/README.md` only if #1433 has not already landed
- Verification commands:
  - `python3 - <<'PY'
from pathlib import Path
for d in [Path('docs/review'), Path('docs/portfolio'), Path('docs/plans'), Path('docs/engineering'), Path('docs/superpowers'), Path('docs/superpowers/plans'), Path('docs/superpowers/specs')]:
    assert (d/'README.md').exists()
print('ok')
PY`
  - `make docs-check`
- Merge order: **4**

### Wave 5 — Optional archival hardening (P2)
- Worker: `W-codex321-docs-archive-hardening`
- Reserved files:
  - `docs/audits/README.md`
  - `docs/SDK_MIGRATION_AUDIT_2026-03-13.md`
  - `docs/SDK_MIGRATION_ROADMAP_2026-03-13.md`
  - `docs/SDK_CANONICAL_REMEDIATION_REPORT_2026-03-15.md`
  - `docs/engineering/dependency-upgrade-blockers-2026-04.md`
- Verification commands:
  - `rg -n "SDK_MIGRATION_|dependency-upgrade-blockers|archive" docs/SDK_* docs/engineering/*`
  - `rg -n "2026-05-07|docs/audits|archive" docs/audits/README.md`
  - `make docs-check`
- Merge order: **5**

## Notes for continuation

- Merged audit PRs #1434-#1437 are useful baselines for index/runtime/subsystem/archive verification.
- Open issues in other areas are tracked by the audit PRs above and #1433; this artifact is intended as the next coordinated plan pass for the docs team to execute with disjoint workers.
