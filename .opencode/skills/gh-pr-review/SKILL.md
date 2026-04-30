---
name: gh-pr-review
description: Use when reviewing a pull request, deciding whether it is safe to merge, or operating the review-to-merge flow in repositories where workflow drift, local verification, SDK-first rules, or runtime/container changes matter.
---

# GitHub PR Review

## Overview

Use this skill to review pull requests with a bug-finding mindset and, when asked, drive them through local verification, merge, and cleanup. Prioritize correctness, regressions, contract drift, data safety, missing validation, and workflow mismatches over style comments or broad rewrite advice.

In repositories that use `AGENTS.md`, local override files, SDK registries, or Docker Compose as part of the product contract, load those first. They are part of correctness, not optional background reading.

For `rag-fresh`, treat this as a `review -> verify -> merge-to-dev -> cleanup` operator unless the user explicitly wants a read-only review.

## Read First

Read these repository files before making merge or approval decisions:

- `AGENTS.md`
- nearest `AGENTS.override.md` for touched paths
- `README.md`
- `DOCKER.md` when the touched surface is runtime-impacting
- `docs/engineering/sdk-registry.md`
- `.claude/rules/sdk-registry.md` only as a compatibility pointer if present
- `Makefile`
- `.github/workflows/ci.yml`
- `scripts/git_hygiene.py`
- `scripts/repo_cleanup.sh`

In `rag-fresh`, `docs/engineering/sdk-registry.md` is the canonical SDK registry. `.claude/rules/sdk-registry.md` is only a backward-compatibility stub.

## Discovery Tools

Follow the repository tool contract from `AGENTS.md`:

- Use project-local `grepai` discovery first for "where does this live?" and non-trivial tracing.
- Prefer `grepai_search` and `grepai_trace_*` without a named workspace unless one was explicitly configured.
- Use `context-mode` for large-output repo exploration and external documentation lookup.
- Use `rg` or direct shell/file reads only for exact strings, imports, symbols, path checks, or small targeted reads.
- Use official docs or Context7 only when SDK or framework behavior is version-sensitive, ambiguous, or looks stale in the local registry/current code.
- Use broad web search only as a fallback after the repo registry, current code, and official docs.

## Operating Rules

- Review against the true merge base, not only the current branch tip.
- Map changed paths to the affected subsystem and runtime services before choosing checks.
- Treat workflow drift as a real finding.
- For `rag-fresh`, expect feature PRs to target `dev`; treat `main` as the deploy branch unless current repo evidence says otherwise.
- Treat local verification as the release authority unless the user or repo contract says otherwise.
- Prefer SDK-native or framework-native solutions already adopted by the repo. Custom layers require a concrete justification.
- For SDK-sensitive changes, do not approve or merge based on intuition alone when the registry/current code is stale or unclear. Verify through Context7 or official docs first.
- Review is read-first by default. Only patch, merge, or clean up when the user asks for it.
- Findings must describe concrete failure modes, not style preferences.

## Workflow

### 1. Load the Repository Contract

Before a deep review, inspect the repo's rules and operating model:

```bash
test -f AGENTS.md && sed -n '1,220p' AGENTS.md
rg --files -g 'AGENTS.override.md'
sed -n '1,220p' README.md
test -f DOCKER.md && sed -n '1,220p' DOCKER.md
test -f docs/engineering/sdk-registry.md && sed -n '1,260p' docs/engineering/sdk-registry.md
test -f .claude/rules/sdk-registry.md && sed -n '1,80p' .claude/rules/sdk-registry.md
rg -n "make check|test-unit|verify-compose-images|git-hygiene|repo-cleanup" Makefile README.md docs .github scripts
test -f .github/workflows/ci.yml && sed -n '1,220p' .github/workflows/ci.yml
test -f scripts/git_hygiene.py && sed -n '1,220p' scripts/git_hygiene.py
test -f scripts/repo_cleanup.sh && sed -n '1,220p' scripts/repo_cleanup.sh
```

If the patch violates explicit repo rules, treat that as a real finding even if the code looks locally reasonable.

### 2. Check Repository Workflow

Before reviewing a PR deeply, determine the repository's real workflow instead of assuming `main`:

```bash
gh pr list --state merged --limit 8 --json number,title,baseRefName,headRefName,mergedAt,url
git branch --show-current
git remote -v
test -f .github/workflows/ci.yml && sed -n '1,220p' .github/workflows/ci.yml
rg -n "make check|test-unit|verify-compose-images|git-hygiene|repo-cleanup" Makefile README.md docs .github scripts
```

Capture these repo-level facts when available:

- normal PR target branch, for example `dev`
- whether `main` is a deploy branch rather than the everyday review branch
- whether local verification or CI is the release authority
- whether cleanup scripts assume a different merge target than the current workflow
- whether the repo enforces SDK-first decisions through a registry or local rules
- which merge strategy matches recent history, for example merge commits vs squash

Treat workflow drift as a real review concern. If docs, scripts, or CI still assume `main` while active PRs land in `dev`, call that out.

### 3. Gather PR Context

If a PR number is available, prefer GitHub CLI plus local git:

```bash
gh pr view <number> --json number,title,body,baseRefName,headRefName,author,changedFiles,files,commits,reviewDecision,mergeStateStatus,statusCheckRollup,mergeCommit
gh pr diff <number>
git fetch origin <base> <head>
git merge-base origin/<base> origin/<head>
git diff <merge-base>..origin/<head> -- <path>
```

If GitHub CLI is unavailable, reconstruct the review locally from the base branch, head branch, and merge base.

Capture these facts before judging the patch:

- PR title and stated intent
- PR body shape: summary, test plan, linked issues, rollout notes
- base branch and head branch
- changed files and high-risk areas
- check status, review status, and mergeability
- whether the diff includes tests, migrations, config changes, or rollout changes
- whether the branch is a feature branch, `dev`, or a `dev -> main` release PR

### 4. Route by Subsystem and Blast Radius

Do not review the diff as a flat list of files. Map it to the real subsystem and service blast radius first.

In repositories like `rag-fresh`, use these rough routes:

- `telegram_bot/**`, `src/retrieval/**`: bot runtime, search, rerank, caching, LangGraph edges
- `src/ingestion/unified/**`, `src/ingestion/docling_*`, `Dockerfile.ingestion`, `docker/ingestion/**`: ingestion flow, manifest state, docling path, Qdrant writes
- `src/voice/**`, `telegram_bot/graph/**`, `docker/livekit/**`: voice agent, RAG API, LiveKit runtime
- `mini_app/**`: mini app backend and frontend
- `compose*.yml`, `docker/**`, `services/**`, `*Dockerfile*`: container and runtime contract
- `k8s/**`: deploy surface and release parity

For `rag-fresh`, the main service groupings are:

- retrieval and bot behavior: `bot`, `mini-app-api`, `rag-api`, `bge-m3`, `qdrant`, sometimes `litellm`
- ingestion behavior: `ingestion`, `docling`, `bge-m3`, `postgres`, `qdrant`
- voice behavior: `voice-agent`, `rag-api`, `livekit-server`, `livekit-sip`, `litellm`
- mini app changes: `mini-app-api`, `mini-app-frontend`

Translate the changed paths into services before you decide what to test, which docs matter, or what can break.

### 5. Inspect the Right Failure Modes

Do not review linearly from top to bottom. Triage by risk:

- public API or schema changes
- state machine or control-flow changes
- auth, permissions, secrets, or trust boundaries
- async, concurrency, caching, retry, timeout, or idempotency behavior
- migrations, backfills, feature flags, deploy scripts, or infra config
- container build, entrypoint, profile, env, healthcheck, or volume changes
- error handling, fallback logic, and observability changes
- tests that changed less than the production code they are meant to protect

Read the full file when a hunk depends on surrounding invariants. Trace callers and callees before claiming a regression.

Treat these as likely findings:

- behavior that now fails for a realistic input or environment
- broken compatibility with existing callers, payloads, or stored data
- missing updates to tests, docs, configs, or migrations required by the change
- silent failure paths, swallowed exceptions, or incorrect fallback behavior
- racy or non-deterministic behavior introduced by the patch
- checks that claim safety but do not cover the risky path

Do not file findings for:

- pure style preferences
- optional refactors unrelated to correctness
- hypothetical risks without a concrete failure mode
- nits better handled as non-blocking suggestions

### 6. SDK-First and Docs Gate

If the repository has an SDK registry or explicit SDK-first rules, read them before accepting custom code paths. In repositories like this one, custom layers are suspect when first-party SDKs or adopted frameworks already cover the behavior.

Use this decision order:

1. Read `docs/engineering/sdk-registry.md`.
2. Match the changed area to the relevant SDK or framework sections.
3. Check current repository usage and local gotchas.
4. Use official docs or Context7 for version-sensitive or ambiguous behavior.
5. Use broad web search only as a fallback.

For `rag-fresh`, if `.claude/rules/sdk-registry.md` exists, treat it as a compatibility pointer only, not the source of truth.

Flag these patterns:

- custom wrappers that duplicate ready-made SDK behavior without product value
- new routing, state, cache, retry, or prompt layers where the adopted SDK already covers the need
- imports or API usage that contradict the local SDK registry
- broad migrations that reopen already-settled keeper-stack decisions
- approvals that rely on memory instead of checking the registry/current code/docs

If the custom code is justified, state why the official SDK path is insufficient for this case.

### 7. Container and Compose Gate

If the diff touches `compose*.yml`, any `Dockerfile*`, `docker/**`, `services/**`, runtime env wiring, or a subsystem whose behavior depends on local services, perform a container-aware review.

Use commands like these:

```bash
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config >/tmp/compose.dev.yaml
COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --compatibility config >/tmp/compose.vps.yaml
COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config --services
COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --compatibility config --services
make verify-compose-images
```

Check these contracts:

- effective service set in dev versus VPS, including profile-gated services
- build context, Dockerfile target, copied paths, extras, and runtime entrypoint
- env vars, ports, volumes, bind mounts, read-only settings, tmpfs, and user/permission model
- healthchecks and readiness assumptions versus the service's real startup behavior
- `depends_on` and startup ordering versus the actual dependency chain
- whether local and VPS compose overrides still preserve the intended release surface

In repositories like `rag-fresh`, treat these as likely findings:

- a release-critical service disappears from the effective config because of profile drift
- `compose.dev.yml` and `compose.vps.yml` no longer preserve parity for a reviewed surface
- a bind mount, manifest path, or data directory semantics change can wipe state or create empty runtime input
- a Dockerfile or entrypoint change breaks non-root execution, write paths, or runtime extras
- a healthcheck reports green before the service is actually ready
- a PR changes images or compose pins without checking runtime image drift

When containers are in scope, mention the service blast radius explicitly in the review summary.

### 8. Verify Before Claiming

Run targeted checks when they can materially confirm or falsify the review:

- unit tests for changed modules
- lint or type checks for touched languages
- integration or smoke checks for boundary changes
- Compose config rendering or service-set checks for runtime changes
- focused reproduction commands for suspicious paths

For `rag-fresh`, separate the lanes:

- review lane: run the smallest relevant command that tests the risky path
- merge lane: for most code changes, run fresh `make check` and `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- runtime lane: if the touched scope is runtime-impacting, also render effective Compose config and run `make verify-compose-images` when image/runtime drift is in scope

Prefer the repo contract over generic advice. Known `rag-fresh` checks:

- `make check`
- `PYTEST_ADDOPTS='-n auto --dist=worksteal' make test-unit`
- `uv run pytest tests/integration/test_graph_paths.py -n auto --dist=worksteal -q` for graph flow changes
- `make ingest-unified-status` and `python -m src.ingestion.unified.cli preflight` for ingestion behavior
- `make test-smoke` or `make test-smoke-routing` for live-routing or release-surface changes
- `COMPOSE_FILE=compose.yml:compose.dev.yml docker compose --compatibility config >/tmp/compose.dev.yaml`
- `COMPOSE_FILE=compose.yml:compose.vps.yml docker compose --compatibility config >/tmp/compose.vps.yaml`
- `make verify-compose-images` when compose pins, images, or runtime services are in play

Green CI does not override a repo that says local verification is authoritative.

If you skip a relevant check, state that explicitly and downgrade confidence.

### 9. Merge Gate

Before merging, check these conditions explicitly:

- there are no unresolved findings that block correctness
- the PR target matches the repository workflow
- the required local verification for the touched surface ran fresh
- SDK-sensitive changes passed the SDK/docs gate
- runtime-impacting changes passed the container/compose gate
- the PR body does not materially misdescribe the diff or test plan
- `mergeStateStatus` does not indicate an unresolved GitHub-side blocker

For `rag-fresh`, apply these branch rules:

- feature PRs should normally merge into `dev`
- `main` should normally receive `dev -> main` release or deploy-oriented PRs, not everyday feature work
- if a feature PR targets `main` while current repo history and workflow show `dev`, treat that as a blocker unless the user says otherwise

If any gate fails, do not merge. Report the blocker and the missing verification instead.

### 10. Autofix Lane

Review is read-first by default. Do not mutate the PR unless the user asks for fixes or the task explicitly includes autofix.

When autofix is requested:

- keep fixes narrow and directly tied to review findings
- prefer SDK-native fixes over adding new custom layers
- rerun the smallest checks that cover the fix
- rerun merge-lane verification if the user also wants the PR merged
- summarize exactly what changed and what was revalidated

If the review uncovers a broad design mismatch, prefer a follow-up plan or issue over an opportunistic rewrite inside the PR.

### 11. Merge Execution

When the user asks to merge and the gates are clean:

1. Reconfirm branch workflow and mergeability.
2. Choose the merge strategy that matches recent repository history.
3. Merge only after fresh local verification is complete.
4. Clean up branches and worktrees in a branch-aware way.

Useful commands:

```bash
gh pr view <number> --json baseRefName,headRefName,mergeStateStatus,reviewDecision,mergeCommit
gh pr list --state merged --limit 8 --json number,baseRefName,headRefName,mergedAt,url
gh pr merge <number> --merge --delete-branch
git fetch --prune
```

For `rag-fresh`, recent `dev` PR history uses merge commits, so prefer `gh pr merge <number> --merge --delete-branch` unless the user or current repo policy says otherwise.

Do not delete long-lived branches like `dev` or `main`. For `dev -> main` release PRs, do not treat `dev` as a disposable feature branch.

### 12. Post-Merge Cleanup

If the user asks for post-merge cleanup, make the cleanup branch-aware. Do not assume merged-to-`main` unless the PR base or repo workflow confirms it.

Useful commands:

```bash
make git-hygiene
make git-hygiene-fix
make repo-cleanup
git branch --merged <base-branch>
git worktree list
git worktree remove <path>
git worktree prune
```

Cleanup rules:

- never delete the current branch or active worktree
- prefer dry-run cleanup first
- if cleanup helpers are hardcoded to an older default, adjust them to the real base branch before trusting the result
- after a `dev -> main` merge, cleanup may be broader because feature branches merged into `dev` can now also be fully merged for release
- keep branch or PR references that are still needed for follow-up review
- if the cleanup includes Compose or worktree state, avoid removing active service directories, bind-mount inputs, or the current worktree

Treat stale local worktrees, merged branches, and transient artifacts as part of done when the repository uses worktree-based delivery.

## Write the Review

Present findings first, ordered by severity. Use file references and explain the failure mode, not just the suspicious line.

For each finding, include:

- severity
- file and line reference
- what breaks
- why the current patch causes it
- what condition triggers it

Use this response shape:

```markdown
Findings

1. High: concise bug title
   File reference and explanation of the regression or risk.

2. Medium: concise bug title
   File reference and explanation of the regression or risk.

Open questions

- Assumption or ambiguity that affects confidence.

Summary

- One short paragraph on overall risk, merge readiness, and verification coverage.
```

If no findings are found, say that explicitly and list residual risks or tests you did not run.

## Review Heuristics

- Prefer one well-supported finding over many weak ones.
- Tie every concern to observable behavior, not taste.
- Check whether tests would actually fail if the bug were real.
- Notice when a PR description and the actual diff do not match.
- Notice when the PR body is missing summary, test plan, linked issue, or rollout context that the repo usually expects.
- Notice when green checks do not cover the changed subsystem.
- Notice when helper scripts or docs still describe an older branch workflow than the merged PR history shows.
- Notice when custom code ignores the repo's SDK-first stack.
- Notice when container config, compose profiles, or Dockerfiles widen the runtime blast radius beyond what the PR body admits.
- Notice when a service is healthy in CI or `docker compose ps` but the reviewed release contract still fails at the endpoint level.
- Escalate missing rollback, migration, or deploy safety when the patch touches production-critical paths.
