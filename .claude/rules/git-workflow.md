---
paths: ".github/**,renovate.json"
---

# Git & PR Workflow

## PR Discipline

| Rule | Standard |
|------|----------|
| **Size** | < 400 lines changed (ideal: < 200). Split larger work into stacked PRs |
| **Scope** | One issue per PR. Title: `type(scope): description` matching commit convention |
| **Linking** | Always include `Closes #N` or `Related #N` in PR body |
| **Branch naming** | `feat/`, `fix/`, `chore/`, `docs/` prefix matching commit type |
| **Rebase policy** | Rebase on `main` before push. Use `--force-with-lease` (never `--force`) |
| **Stale branches** | Delete after merge. `make git-hygiene` for audit |

## Bug Handling During PR Review

| Found during review | Action |
|---------------------|--------|
| Bug **in PR code** (new/changed lines) | PR review comment → author fixes in same PR |
| **Pre-existing** bug (existed before PR) | New issue with `Found during #PR` in description |
| **CI flake** (unrelated to PR) | New issue with label `flaky-test` |
| **Conflict** with another PR | PR comment, coordinate merge order |

**Rule:** PR fixes only what's in scope. Everything else → separate issue. Don't bloat PRs with unrelated fixes.

## Merge Discipline

- PRs merge only with green CI (lint + unit shards + integration)
- Rebase-merge preferred (clean linear history)
- No self-merge for non-trivial changes without review or CI pass
- Renovate PRs: batch during stable CI windows (see below)

## Renovate PR Handling

Current config: `renovate.json` | Schedule: Monday before 9:00 Kyiv

| Update Type | Strategy | Auto-merge |
|-------------|----------|------------|
| **Patch** (all) | Individual PR | Yes |
| **Minor** (databases, core libs, pre-commit) | Grouped PR | Yes |
| **Minor** (ML, RAG stack, bot) | Grouped PR | No — review changelogs |
| **Major** (all) | Individual PR | No — manual review required |
| **Lock maintenance** | Weekly Monday 5am | Yes |

**Batching strategy:**
- `platformAutomerge: true` — GitHub merges automatically after CI passes
- `prHourlyLimit: 5` — prevents PR flood
- Groups: databases, ml-platform, ai-services, monitoring, python-core-libs, python-ml-libs, python-rag-stack, python-bot, python-dev-tools, github-actions
- Review with `/deps` skill for audit workflow

**When CI is red:** Do not merge Renovate PRs. Fix CI first, then let automerge catch up.

## Branch Cleanup

```bash
make git-hygiene          # Audit report: stale branches, orphan worktrees
make git-hygiene-fix      # Auto-cleanup merged branches
```

- Merged branches: delete immediately after merge
- Stale feature branches (> 30 days, no activity): close PR with comment, delete branch
- Worktrees: clean up after feature completion
