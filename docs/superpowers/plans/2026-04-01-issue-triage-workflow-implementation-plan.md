# Issue Triage Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Codify the approved issue-triage workflow into persistent repo guidance, implement it from an isolated git worktree, and finish with a pull request into the repo's active integration branch.

**Architecture:** Keep the implementation documentation-first. Start from an isolated worktree rooted off `dev`, put stable rules in `AGENTS.md`, put the operator-facing decision process in `docs/engineering/issue-triage.md`, and keep the current backlog classification in a dated snapshot document so it can expire cleanly without mutating canonical policy. Finish by pushing the worktree branch and opening a PR against `dev`, because recent merged PRs in this repository target `dev` even though deploys happen from `main`.

**Tech Stack:** Markdown, GitHub CLI (`gh`), repo guidance docs, Context7, `rg`

---

## Scope

**In scope**
- Create and use a dedicated worktree under `.worktrees/` for implementation.
- Create a reusable issue triage playbook for future sessions.
- Update root `AGENTS.md` with canonical triage guidance and a pointer to the detailed playbook.
- Publish a dated backlog snapshot using the approved lanes from the spec.
- Verify the new docs stay consistent with the approved spec and current backlog command.
- Push the implementation branch and open a PR against `dev` at the end.

**Out of scope**
- Implementing or closing any product issue.
- Adding GitHub automation, scripts, or new labels for triage.
- Refactoring subsystem code while documenting the workflow.
- Expanding this into per-subsystem overrides before the root workflow proves useful.
- Merging directly into `main`.

## File Map

- Create: `docs/engineering/issue-triage.md`
  Purpose: concise operator playbook for choosing `Quick execution`, `Plan needed`, or `Design first`, including `@sdk-research`, `@brainstorming`, `@writing-plans`, and `@executing-plans` handoffs.
- Modify: `AGENTS.md`
  Purpose: root-session guidance that points to the playbook and makes the triage lane decision part of normal repo workflow.
- Create: `docs/plans/2026-04-01-open-issues-triage-snapshot.md`
  Purpose: dated snapshot of the currently discussed backlog candidates so the next session can start from an explicit shortlist without treating it as timeless policy.
- Reference: `docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md`
  Purpose: approved design source of truth. Do not drift from it during implementation.

## Workflow Reality To Preserve

- Current local integration branch: `dev`
- Recent merged PR base branch: `dev`
- CI runs on pull requests to both `main` and `dev`
- VPS deploy runs only on pushes to `main`

Because of that, this plan should execute in a dedicated branch off `dev` and finish with a PR back into `dev`, not a direct merge to `main`.

## Verification Strategy

This is a docs/process change, not a product-code change. Use targeted consistency checks and commit-hook hygiene instead of forcing full repo test suites for no-runtime edits.

- Use `rg` checks to verify required sections, lane names, and cross-references exist.
- Use `gh issue list ... --json ...` to confirm the snapshot still matches the current backlog at write time.
- Use `git diff --check` before claiming completion.
- If implementation grows beyond docs/process files, expand verification to the repo-wide checks required by `AGENTS.md`.

### Task 0: Create The Isolated Worktree

**Files:**
- Reference: `.gitignore`
- Reference: `AGENTS.md`

- [ ] **Step 1: Confirm the worktree location is the repo default**

Run: `ls -d .worktrees`

Expected: output includes `.worktrees`.

Run: `git check-ignore -v .worktrees`

Expected: output shows `.gitignore:195:.worktrees/	.worktrees` or an equivalent ignore rule confirming the directory is ignored.

- [ ] **Step 2: Create the worktree from the active integration branch**

Run: `git worktree add .worktrees/issue-triage-workflow -b docs/2026-04-01-issue-triage-workflow dev`

Expected: a new worktree is created at `.worktrees/issue-triage-workflow` and the new branch `docs/2026-04-01-issue-triage-workflow` is checked out there.

- [ ] **Step 3: Switch to the worktree and verify branch state**

Run: `cd .worktrees/issue-triage-workflow && git branch --show-current && git status --short`

Expected:
- current branch is `docs/2026-04-01-issue-triage-workflow`
- working tree is clean

- [ ] **Step 4: Record the execution contract**

Before changing files, note in the session that:
- implementation is now running from `.worktrees/issue-triage-workflow`
- `dev` is the PR base branch for this work
- final branch completion must use `@finishing-a-development-branch` with the PR option unless the user explicitly chooses another completion path

- [ ] **Step 5: Commit**

No commit in this task. Worktree setup is preparatory only.

### Task 1: Create The Operator Playbook

**Files:**
- Create: `docs/engineering/issue-triage.md`
- Reference: `docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md`

- [ ] **Step 1: Define the docs contract**

The new playbook must contain these sections:

```markdown
# Issue Triage
## Decision Model
## Research Order
## Execution Lanes
## DRY, SOLID, and Reuse
## Session Checklist
```

It must also mention:
- `docs/engineering/sdk-registry.md`
- Context7
- `@sdk-research`
- `@brainstorming`
- `@writing-plans`
- `@executing-plans`

- [ ] **Step 2: Run the precondition check**

Run: `test -f docs/engineering/issue-triage.md`

Expected: exit code `1` because the playbook does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `docs/engineering/issue-triage.md` with content shaped like:

```markdown
# Issue Triage

## Decision Model
- Classify each issue by `scope`, `risk`, `SDK coverage`, and `reuse pressure`.

## Research Order
1. `docs/engineering/sdk-registry.md`
2. current code usage
3. Context7 / official docs
4. broad web search only as fallback

## Execution Lanes
### Quick execution
- local change
- established contract
- narrow verification

### Plan needed
- multi-file or runtime-sensitive work
- route through `@writing-plans`, then `@executing-plans`

### Design first
- ambiguous structure or cross-boundary changes
- route through `@brainstorming` before planning

## DRY, SOLID, and Reuse
- prefer local fixes when the abstraction is not yet stable
- extract only after shared shape is proven

## Session Checklist
1. shortlist backlog candidates
2. inspect touched surfaces
3. run `@sdk-research` when SDK/framework behavior matters
4. choose one lane
5. start exactly one issue
```

Keep the prose concise. The playbook should summarize the approved spec, not duplicate every paragraph.

- [ ] **Step 4: Run the docs check**

Run: `rg -n "^## (Decision Model|Research Order|Execution Lanes|DRY, SOLID, and Reuse|Session Checklist)$|@sdk-research|@brainstorming|@writing-plans|@executing-plans|Context7|docs/engineering/sdk-registry.md" docs/engineering/issue-triage.md`

Expected: matches for all five headings and all required references.

- [ ] **Step 5: Commit**

```bash
git add docs/engineering/issue-triage.md
git commit -m "docs: add issue triage operator playbook"
```

### Task 2: Codify The Workflow In Root Repo Guidance

**Files:**
- Modify: `AGENTS.md`
- Reference: `docs/engineering/issue-triage.md`
- Reference: `docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md`

- [ ] **Step 1: Define the failing check**

`AGENTS.md` must reference the new playbook and must name the three execution lanes directly:

```markdown
## Issue Triage Workflow
- Before starting a new issue, classify it as `Quick execution`, `Plan needed`, or `Design first`.
- Use `docs/engineering/issue-triage.md` as the operator playbook.
```

- [ ] **Step 2: Run the pre-change check**

Run: `rg -n "Issue Triage Workflow|docs/engineering/issue-triage.md|Quick execution|Plan needed|Design first" AGENTS.md`

Expected: no match for `Issue Triage Workflow` or `docs/engineering/issue-triage.md`.

- [ ] **Step 3: Write the minimal implementation**

Add a short section to `AGENTS.md` near the workflow/process guidance with content shaped like:

```markdown
## Issue Triage Workflow
- Before starting a new issue, classify it as `Quick execution`, `Plan needed`, or `Design first`.
- Use `docs/engineering/issue-triage.md` as the detailed operator playbook.
- Keep small local fixes local; route runtime, migration, refactor, or contract-changing work through planning or design first.
- For SDK-sensitive work, keep the lookup order: registry -> current code -> Context7 -> broad web fallback.
- `Plan needed` work routes through `@writing-plans`; `Design first` work routes through `@brainstorming` first.
```

Do not paste the entire spec into `AGENTS.md`; keep it short and authoritative.

- [ ] **Step 4: Run the verification check**

Run: `rg -n "Issue Triage Workflow|docs/engineering/issue-triage.md|Quick execution|Plan needed|Design first|@writing-plans|@brainstorming|Context7" AGENTS.md`

Expected: matches for the new section title, the playbook path, the three lanes, and the skill references.

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md
git commit -m "docs: codify issue triage workflow in agents"
```

### Task 3: Publish A Dated Backlog Snapshot

**Files:**
- Create: `docs/plans/2026-04-01-open-issues-triage-snapshot.md`
- Reference: `docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md`

- [ ] **Step 1: Define the snapshot contract**

The snapshot must record:
- the retrieval date;
- the exact `gh issue list` command used;
- the agreed immediate candidates for `Quick execution`, `Plan needed`, and `Design first`;
- a separate `Needs discovery / defer` bucket for open issues not yet classified confidently.

Use this file shape:

```markdown
# 2026-04-01 Open Issues Triage Snapshot

Source command:
`gh issue list --state open --limit 30 --json number,title,labels,assignees,updatedAt,url`

## Quick execution
- #1075 ...

## Plan needed
- #1071 ...

## Design first
- #1070 ...

## Needs discovery / defer
- #1072 ...
```

- [ ] **Step 2: Run the precondition check**

Run: `test -f docs/plans/2026-04-01-open-issues-triage-snapshot.md`

Expected: exit code `1` because the dated snapshot does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `docs/plans/2026-04-01-open-issues-triage-snapshot.md` using the issues already agreed in the design:

```markdown
## Quick execution
- #1075
- #1076
- #1078
- #1079

## Plan needed
- #1071
- #1073
- #1074
- #1080
- #1081
- #1082
- #1083

## Design first
- #1070
```

For everything not explicitly classified in the approved design, place it under `Needs discovery / defer` rather than inventing certainty.

- [ ] **Step 4: Re-run the backlog command and verify the snapshot**

Run: `gh issue list --state open --limit 30 --json number,title,labels,assignees,updatedAt,url`

Expected: the returned issue set still contains `#1070`, `#1071`, `#1073`, `#1074`, `#1075`, `#1076`, `#1078`, `#1079`, `#1080`, `#1081`, `#1082`, and `#1083`. If the backlog changed materially, refresh the snapshot before committing.

Run: `rg -n "#1070|#1071|#1073|#1074|#1075|#1076|#1078|#1079|#1080|#1081|#1082|#1083|Needs discovery / defer" docs/plans/2026-04-01-open-issues-triage-snapshot.md`

Expected: matches for all agreed issue IDs plus the defer bucket heading.

- [ ] **Step 5: Commit**

```bash
git add docs/plans/2026-04-01-open-issues-triage-snapshot.md
git commit -m "docs: add dated open issues triage snapshot"
```

### Task 4: Verify Cross-References And Finish Cleanly

**Files:**
- Modify if needed: `AGENTS.md`
- Modify if needed: `docs/engineering/issue-triage.md`
- Modify if needed: `docs/plans/2026-04-01-open-issues-triage-snapshot.md`

- [ ] **Step 1: Run the cross-reference check**

Run: `rg -n "docs/engineering/issue-triage.md|docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md|Quick execution|Plan needed|Design first|Context7" AGENTS.md docs/engineering/issue-triage.md docs/plans/2026-04-01-open-issues-triage-snapshot.md`

Expected: the lane names are spelled consistently, the playbook path is present, and the new docs still align with the approved spec.

- [ ] **Step 2: Run the cleanliness check**

Run: `git diff --check`

Expected: no whitespace errors, malformed conflict markers, or patch-format problems.

- [ ] **Step 3: Confirm the worktree is clean**

Run: `git status --short`

Expected: clean working tree after the task commits above. If not clean, inspect the remaining diff and either commit the intended wording fix or explicitly document why it remains.

- [ ] **Step 4: Commit only if Task 4 changed files**

```bash
git add AGENTS.md docs/engineering/issue-triage.md docs/plans/2026-04-01-open-issues-triage-snapshot.md
git commit -m "docs: normalize issue triage workflow references"
```

Skip this commit if no files changed during Task 4.

### Task 5: Push The Branch And Create The PR

**Files:**
- Modify if needed: `AGENTS.md`
- Modify if needed: `docs/engineering/issue-triage.md`
- Modify if needed: `docs/plans/2026-04-01-open-issues-triage-snapshot.md`

- [ ] **Step 1: Re-run the final verification from inside the worktree**

Run: `cd .worktrees/issue-triage-workflow && rg -n "Issue Triage Workflow|docs/engineering/issue-triage.md|Quick execution|Plan needed|Design first|Context7" AGENTS.md docs/engineering/issue-triage.md docs/plans/2026-04-01-open-issues-triage-snapshot.md && git diff --check && git status --short`

Expected:
- the cross-reference matches are present
- `git diff --check` prints nothing
- `git status --short` is clean except for any intentional final doc edits that still need a commit

- [ ] **Step 2: Use the branch-finishing workflow**

Invoke `@finishing-a-development-branch` from inside `.worktrees/issue-triage-workflow`.

Because this repository's recent merged PRs target `dev`, choose the PR path unless the user explicitly asks for another option:

```text
Implementation complete. What would you like to do?

1. Merge back to dev locally
2. Push and create a Pull Request
3. Keep the branch as-is (I'll handle it later)
4. Discard this work
```

Expected default for this plan: option `2`.

- [ ] **Step 3: Push and create the PR against `dev`**

Run:

```bash
cd .worktrees/issue-triage-workflow
git push -u origin docs/2026-04-01-issue-triage-workflow
gh pr create --base dev --head docs/2026-04-01-issue-triage-workflow --title "docs: codify issue triage workflow" --body "$(cat <<'EOF'
## Summary
- add the operator playbook for issue triage
- codify the triage workflow in AGENTS.md
- publish a dated backlog triage snapshot

## Test Plan
- [x] verify required headings and references with rg
- [x] verify current backlog ids with gh issue list
- [x] run git diff --check
EOF
)"
```

Expected:
- branch is pushed with upstream tracking
- a PR URL is returned
- the PR targets `dev`

- [ ] **Step 4: Preserve the worktree after PR creation**

Do not remove `.worktrees/issue-triage-workflow` immediately after opening the PR. Keep it available for review feedback unless the user explicitly asks for cleanup after the PR is created or merged.

- [ ] **Step 5: Commit**

No commit in this task. The branch should already contain the task commits above.

## Guardrails

- Do not let the implementation drift into fixing any of the backlog issues themselves.
- Do not automate triage labels or issue updates in this plan; prove the manual workflow first.
- Keep `AGENTS.md` concise; detailed operating instructions belong in `docs/engineering/issue-triage.md`.
- Treat the dated snapshot as disposable evidence, not as timeless source of truth.
- Before claiming completion, apply `@verification-before-completion` thinking even though this is docs-only work.
- Use `.worktrees/issue-triage-workflow` for implementation; do not execute this plan directly on the shared `dev` worktree.
