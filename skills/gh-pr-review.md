---
name: gh-pr-review
description: Use when reviewing PRs, processing open PR queue, auto-fixing style, running tests, or merging to dev. Solo-dev workflow: analyze → auto-fix → test → classify failures → handoff → merge. Triggers on "review PR", "process PRs", "merge PR", "fix PR", "open PRs".
---

# gh-pr-review — Solo Dev PR Workflow

## Purpose

Review, fix, test, and merge PRs into `dev`. Works without chat context via PR handoff. Never blocks on offline self-hosted runners.

## Quick Flow

```
PR → fresh dev check → diff → risk → auto-fix → tests → classify fails → handoff → merge/fix/block
```

## Repo Rules

- Base branch: `dev`
- Merge strategy: merge commit
- Never merge into `main` without explicit instruction
- Never change branch protection
- Never mark test as passed unless it actually passed on current PR head
- If PR head changed after validation → validation is stale, rerun

## Autopilot Mode

When explicitly requested, the agent may review, auto-fix, validate, and merge a PR into `dev`.

### Allowed for autopilot

- docs
- style
- test
- normal code changes

### Restricted (fix + validate, but no merge if uncertain)

- runtime changes
- Docker / Compose / env changes
- LiteLLM / Qdrant / LangChain integration changes
- dependency changes
- security-sensitive changes

Runtime/security PR can be merged by autopilot only if:
- make ci-local passed
- required GitHub checks green
- no env_failure related to changed subsystem
- no security uncertainty
- findings explicitly say clean

### Autopilot flow

1. Read the PR and current Agent Handoff.
2. Verify that the PR targets `dev`.
3. Fetch latest `origin/dev`.
4. Validate the PR branch against fresh `dev`.
5. Classify risk.
6. Run required validation:
   - Ruff format
   - Ruff lint
   - make test
   - make test-contract
7. If tests fail, classify the failure:
   - code_regression
   - stale_test
   - env_failure
   - flaky_or_race
8. Auto-fix only when safe.
9. Commit fixes to the PR branch.
10. Rerun full required validation.
11. Update PR body Agent Handoff.
12. Add Agent Run comment.
13. Merge into `dev` only if all merge conditions are satisfied.

### Safe auto-fix allowed

- Ruff formatting
- Ruff auto-fixable lint
- import sorting
- stale tests confirmed by current repository architecture
- code regressions where the test is valid and the fix is local and clear

### Auto-fix not allowed

- deleting tests
- broad skip or xfail
- weakening assertions
- changing dependencies
- changing branch protection
- changing production logic only to satisfy a bad test
- hiding env failures as passed

### Test auto-fix rule

If failure class is `stale_test`, update the test to assert current behavior while preserving coverage.

Example: Old LiteLLM Docker proxy expectations must be replaced with in-process LiteLLM router expectations.

Do not delete the test.
Do not skip the test.
Do not weaken the assertion.

### Merge conditions

The agent may merge into `dev` only when ALL are true:

- PR base is `dev`
- current PR head equals `Validated commit`
- working tree is clean
- Ruff format passed
- Ruff lint passed
- make test passed
- make test-contract passed
- required GitHub checks are green
- optional/self-hosted checks are ignored if not required
- no unresolved findings
- no security uncertainty
- no related env_failure remains
- no related flaky_or_race remains

If a new commit is pushed after validation, validation is stale and must be rerun.

If GitHub required checks are red, do not merge.

If only optional/self-hosted checks are red or offline, do not block solo-dev merge.

### After merge

- update PR body status to `merged` if possible
- add Agent Run comment with final validation
- remove or update queue labels

## Risk Classification

| Risk | Examples | Verification |
|---|---|---|
| docs | README, docs, comments | format/link sanity if relevant |
| style | Ruff, formatting only | Ruff format + lint |
| test | tests only | targeted pytest + make test |
| code | production code, refactor | make ci-local |
| runtime | LiteLLM, Qdrant, LangChain, Compose, Docker, env | make ci-local + subsystem checks |
| security | auth, secrets, deps, tokens | make ci-local + manual review, no auto-merge if uncertain |

## Verification Commands

If Makefile targets exist, use them. Otherwise run explicit commands:

```bash
# Fast (style + unit)
uv run ruff format --check src/ telegram_bot/ mini_app/ services/ scripts/
uv run ruff check src/ telegram_bot/ mini_app/ services/ scripts/
make test

# Full local CI
make test-contract

# Release gate
make test-full
```

## Auto-fix Rules

Allowed without asking:
- Ruff format
- Ruff auto-fixable lint
- import sorting
- trailing whitespace
- obvious test path/name updates after confirmed file move

Allowed only after failure classification:
- stale test updates
- code regression fixes
- env/config contract updates

Never do silently:
- delete tests
- broad skip/xfail
- weaken assertions
- change production logic just to satisfy tests
- change dependencies
- change branch protection

## Test Failure Classification

When tests fail, classify before fixing:

| Class | Meaning | Action |
|---|---|---|
| code_regression | test is valid, changed code broke it | fix production code, keep/add regression coverage, rerun |
| stale_test | test asserts removed old architecture | update assertions to current behavior, preserve coverage, rerun |
| env_failure | missing Docker/services/API keys/env | non-blocking if optional; blocker if PR touches that subsystem |
| flaky_or_race | nondeterministic/shared state/timing | stabilize if related to changed code; otherwise report as known |

### LiteLLM Architecture Rule

Current architecture: in-process LiteLLM router. Mandatory fast tests must NOT require removed Docker LiteLLM proxy/config.

Stale references to update in mandatory tests:
- `docker/litellm/config.yaml`
- Kubernetes LiteLLM proxy image
- old Docker proxy default config
- required running LiteLLM HTTP proxy

Replacement coverage should verify:
- in-process router config
- model routing
- fallback behavior
- env parsing
- error handling
- observability

### Stale Test Rule

`stale_test` does NOT mean delete the test. Do not skip, xfail, or weaken. Rewrite to cover new architecture.

## Agent Handoff

Every PR must contain this section in PR body:

```md
## Agent Handoff

Status: ready_for_review | fixing | blocked | clean | merged
Base: dev
Head: <branch>
Validated commit: <sha or none>
Risk: docs | style | test | code | runtime | security
Failure class: none | code_regression | stale_test | env_failure | flaky_or_race

## Validation

- [ ] Ruff format: not run
- [ ] Ruff lint: not run
- [ ] make test: not run
- [ ] make test-contract: not run

## Findings

- None

## Next action

<what the next worker should do>
```

## Agent Run Comment

After every meaningful worker run, add PR comment:

```md
## Agent Run

Worker: codex-web
Commit: <sha>
Action: <review | auto-fix | validation | merge>
Result: <clean | fixing | blocked | merged>

Validation:
- Ruff format: <passed | failed | not run>
- Ruff lint: <passed | failed | not run>
- make test: <passed | failed | not run>
- make test-contract: <passed | failed | not run>

Next worker:
- Re-check that PR head is still <sha>.
- If head changed, rerun validation.
- If unchanged and required GitHub checks are green, continue with decision.
```

## Labels

Queue:
- `agent:ready-review`
- `agent:fixing`
- `agent:blocked`
- `agent:clean`

Risk:
- `risk:docs`
- `risk:style`
- `risk:test`
- `risk:code`
- `risk:runtime`
- `risk:security`

Failure:
- `failure:stale-test`
- `failure:code-regression`
- `failure:env`
- `failure:flaky`

## Freshness Check

Before trusting Validation, compare PR body `Validated commit` with current PR head:

```bash
VALIDATED=$(gh pr view <PR> --json body --jq '.body' | grep "Validated commit" | awk '{print $NF}')
HEAD=$(gh pr view <PR> --json headRefOid --jq '.headRefOid')

if [ "$VALIDATED" != "$HEAD" ]; then
  echo "STALE: rerun validation"
fi
```

## Merge Decision Tree

```
if current head != Validated commit:
    rerun validation

if all required local verification green
and required GitHub checks green
and no unresolved findings:
    update PR body Status: clean
    merge into dev using merge commit

if stale_test:
    update tests while preserving coverage
    rerun validation
    merge only if green

if code_regression:
    fix production code
    keep/add regression coverage
    rerun validation
    merge only if green

if env_failure:
    if optional or unrelated to changed subsystem:
        report clearly and allow solo-dev merge
    else:
        block until environment or test tier is fixed

if flaky_or_race:
    if related to changed code:
        stabilize before merge
    else:
        report as known/unrelated and allow solo-dev merge

if required GitHub checks are red:
    wait or fix required CI
    optional/self-hosted red checks do not block dev merge

if security uncertainty:
    block
    do not auto-merge
```

## Quick Commands

```bash
# Get PR context
gh pr view <PR> --json number,title,body,headRefName,headRefOid,baseRefName,mergeStateStatus,statusCheckRollup,labels

# See diff
gh pr diff <PR>

# Check status
gh pr checks <PR>

# Update PR body
gh pr edit <PR> --body-file /tmp/pr-body.md

# Add comment
gh pr comment <PR> --body-file /tmp/pr-comment.md

# Merge
gh pr merge <PR> --merge

# Filter by label
gh pr list --base dev --label agent:ready-review
```

## Open PR Queue Processing

When asked to "process open PRs", "handle PR queue", or "review all PRs":

### Step 1: Get Current Queue

```bash
# List all open PRs targeting dev
gh pr list --base dev --state open --json number,title,headRefName,headRefOid,baseRefName,mergeStateStatus,labels,createdAt --jq '.[] | "#\(.number): \(.title) | branch=\(.headRefName) | state=\(.mergeStateStatus)"'

# Or filter by label
gh pr list --base dev --label agent:ready-review
gh pr list --base dev --label agent:blocked
```

### Step 2: Classify Each PR

For each PR, determine:

1. **Risk level**: docs / style / test / code / runtime / security
2. **Current status**: has Agent Handoff? is it stale?
3. **GitHub checks**: green / red / pending
4. **Merge conflicts**: yes / no

### Step 3: Process Each PR

For each PR in the queue:

```bash
# 1. Get full context
gh pr view <PR> --json number,title,body,headRefName,headRefOid,baseRefName,mergeStateStatus,statusCheckRollup,labels

# 2. Check freshness
VALIDATED=$(gh pr view <PR> --json body --jq '.body' | grep "Validated commit" | awk '{print $NF}')
HEAD=$(gh pr view <PR> --json headRefOid --jq '.headRefOid')

# 3. If stale or no handoff, run full validation
# 4. Auto-fix if safe
# 5. Run tests
# 6. Classify failures
# 7. Update PR body with Agent Handoff
# 8. Add Agent Run comment
# 9. Set labels
# 10. Merge if clean
```

### Step 4: Priority Order

Process PRs in this order:

1. `agent:ready-review` — already validated, just check freshness and merge
2. `agent:clean` — clean, just needs merge
3. No labels — fresh PR, needs full review
4. `agent:fixing` — in progress, check status
5. `agent:blocked` — blocked, report why

### Step 5: Batch Processing Script

```bash
# Process all ready-review PRs
for PR in $(gh pr list --base dev --label agent:ready-review --json number --jq '.[].number'); do
  echo "Processing PR #$PR..."

  # Check freshness
  VALIDATED=$(gh pr view "$PR" --json body --jq '.body' | grep "Validated commit" | awk '{print $NF}')
  HEAD=$(gh pr view "$PR" --json headRefOid --jq '.headRefOid')

  if [ "$VALIDATED" = "$HEAD" ]; then
    # Fresh, check REQUIRED GitHub checks only (ignore optional/self-hosted)
    BLOCKING=$(gh pr checks "$PR" --required --json bucket,name,state \
      --jq '.[] | select(.bucket != "pass" and .bucket != "skipping") | "\(.name): \(.bucket) \(.state)"' \
      | head -1)
    if [ -z "$BLOCKING" ]; then
      echo "PR #$PR: required checks green, merging..."
      gh pr merge "$PR" --merge
    else
      echo "PR #$PR: required checks not green: $BLOCKING"
    fi
  else
    echo "PR #$PR: stale validation, needs rerun"
  fi
done
```

### Queue Processing Rule

Open PR queue mode reviews and updates handoff by default. It may merge only if the user explicitly requested autopilot merge.

### Step 6: Update Labels After Processing

```bash
# Set ready-review after validation passes
gh pr edit <PR> --add-label "agent:ready-review"

# Set fixing during work
gh pr edit <PR> --add-label "agent:fixing" --remove-label "agent:ready-review"

# Set blocked if cannot proceed
gh pr edit <PR> --add-label "agent:blocked" --remove-label "agent:ready-review"

# Set clean after all checks pass
gh pr edit <PR> --add-label "agent:clean" --remove-label "agent:ready-review"
```

### Quick Start

To start processing open PRs right now:

```bash
# 1. See what's open
gh pr list --base dev --state open

# 2. Pick first PR
PR=<number>

# 3. Checkout PR branch and merge fresh dev
gh pr checkout "$PR"
git fetch origin
git merge --no-edit origin/dev || {
  echo "BLOCKED: merge conflict with origin/dev"
  exit 1
}

# 4. Run validation
make ci-local

# 5. Update handoff
gh pr edit "$PR" --body-file /tmp/pr-body.md

# 6. Merge if clean (only if autopilot explicitly requested)
gh pr merge "$PR" --merge
```
