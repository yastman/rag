---
paths: ".github/**,renovate.json,.claude/rules/git-workflow.md"
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
| **Minor** (databases, core libs, pre-commit-hooks) | Grouped PR | Yes |
| **Minor** (ML, RAG stack, bot, api-clients) | Grouped PR | No — review changelogs |
| **Major** (all) | Individual PR | No — manual review required |
| **Lock maintenance** | Weekly Monday 5am | Yes |
| **Langfuse Docker** | Pinned (disabled) | No — upstream bug #11924 |

**Batching strategy:**
- `platformAutomerge: true` — GitHub merges automatically after CI passes
- `prHourlyLimit: 5` — prevents PR flood
- Groups: databases, ml-platform, ai-services, monitoring, storage, python-base, uv-base, python-core-libs, python-ml-libs, python-rag-stack, python-bot, python-docling, python-api-clients, python-dev-tools, pre-commit-hooks, github-actions
- Review with `/deps` skill for audit workflow

**When CI is red:** Do not merge Renovate PRs. Fix CI first, then let automerge catch up.

## Branch Cleanup

```bash
make git-hygiene          # Audit report: stale branches, orphan worktrees
make git-hygiene-fix      # Auto-cleanup merged branches
```

- Merged branches: delete immediately after merge
- Stale feature branches (> 30 days, no activity): close PR with comment, delete branch
- Worktrees: clean up after feature completion (`git worktree remove <path>`)

## Parallel Sessions & Git Worktrees

**Problem:** Multiple sessions/agents sharing one repo switch branches simultaneously → files change under each other, tests fail on wrong code, edits get lost.

**Rule:** When 2+ sessions or agents work on different branches — each MUST use its own worktree.

### Method 1: `claude --worktree` (recommended)

```bash
# User sessions — each terminal gets isolated worktree
claude --worktree feature-auth    # → .claude/worktrees/feature-auth/, branch worktree-feature-auth
claude --worktree bugfix-123      # → .claude/worktrees/bugfix-123/, branch worktree-bugfix-123
claude --worktree                 # → random name (e.g. bright-running-fox)
```

- Worktrees: `<repo>/.claude/worktrees/<name>/` (in .gitignore)
- Branch: `worktree-<name>`, based on HEAD (note: agents should base off `dev`, not `main`)
- Cleanup: auto-remove if no changes; prompt if changes exist
- Subagents: `isolation: worktree` in agent frontmatter
- **GrepAI:** run `grepai init --inherit --yes` in new worktree to inherit index config

### Method 2: Manual `git worktree` (custom paths/branches)

```bash
# Create worktree based on dev (not main!)
git worktree add /home/user/projects/rag-fresh-wt-{name} -b feat/{name} dev

# Init grepai index (inherits config from main worktree)
cd /home/user/projects/rag-fresh-wt-{name} && grepai init --inherit --yes

# Agent works in its own directory — no branch conflicts
# After done: merge feat branch into dev, then clean up
git checkout dev && git merge feat/{name}
git worktree remove /home/user/projects/rag-fresh-wt-{name}
```

### When to use what

| Scenario | Approach |
|----------|----------|
| 1 session, 1 task | Normal work in `dev` branch |
| 2+ user sessions | `claude --worktree <name>` per terminal |
| 2+ agents, different PRs | Each agent: `isolation: worktree` or manual worktree |
| Lead + workers | Lead in `dev`, workers in worktrees |
| Specific existing branch | Manual: `git worktree add <path> -b feat/xxx dev` |

**In agent team prompts:** Include working directory path explicitly:
```
Working directory: /home/user/projects/rag-fresh-wt-pr280
Branch: claude/optimize-test-suite-RBhOe (already checked out)
Do NOT switch branches. Do NOT cd to other directories.
```

**Cleanup:** `git worktree list` → `git worktree remove <path>` for completed work. `make git-hygiene` includes orphan worktree check.

## CI/CD Pipeline

`.github/workflows/ci.yml`: lint (ruff + mypy) → full-stack deploy (SSH → git pull → docker compose up -d)

Тесты гоняются **локально** перед merge (`make check && make test-unit`). CI только lint + deploy.

**Деплой:** `make deploy-bot` | `gh workflow run ci.yml` | `./scripts/deploy-vps.sh` (`--clean` для пересоздания)

**VPS:** `ssh vps` → `/opt/rag-fresh` → `.claude/rules/k3s.md`
