***REMOVED*** Issue Triage Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Codify the approved issue-triage workflow into persistent repo guidance and publish one dated backlog snapshot that can drive the next execution session.

**Architecture:** Keep the implementation documentation-first. Put stable rules in `AGENTS.md`, put the operator-facing decision process in `docs/engineering/issue-triage.md`, and keep the current backlog classification in a dated snapshot document so it can expire cleanly without mutating canonical policy. Do not automate GitHub labels or issue routing until the manual flow proves insufficient.

**Tech Stack:** Markdown, GitHub CLI (`gh`), repo guidance docs, Context7, `rg`

---

***REMOVED******REMOVED*** Scope

**In scope**
- Create a reusable issue triage playbook for future sessions.
- Update root `AGENTS.md` with canonical triage guidance and a pointer to the detailed playbook.
- Publish a dated backlog snapshot using the approved lanes from the spec.
- Verify the new docs stay consistent with the approved spec and current backlog command.

**Out of scope**
- Implementing or closing any product issue.
- Adding GitHub automation, scripts, or new labels for triage.
- Refactoring subsystem code while documenting the workflow.
- Expanding this into per-subsystem overrides before the root workflow proves useful.

***REMOVED******REMOVED*** File Map

- Create: `docs/engineering/issue-triage.md`
  Purpose: concise operator playbook for choosing `Quick execution`, `Plan needed`, or `Design first`, including `@sdk-research`, `@brainstorming`, `@writing-plans`, and `@executing-plans` handoffs.
- Modify: `AGENTS.md`
  Purpose: root-session guidance that points to the playbook and makes the triage lane decision part of normal repo workflow.
- Create: `docs/plans/2026-04-01-open-issues-triage-snapshot.md`
  Purpose: dated snapshot of the currently discussed backlog candidates so the next session can start from an explicit shortlist without treating it as timeless policy.
- Reference: `docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md`
  Purpose: approved design source of truth. Do not drift from it during implementation.

***REMOVED******REMOVED*** Verification Strategy

This is a docs/process change, not a product-code change. Use targeted consistency checks and commit-hook hygiene instead of forcing full repo test suites for no-runtime edits.

- Use `rg` checks to verify required sections, lane names, and cross-references exist.
- Use `gh issue list ... --json ...` to confirm the snapshot still matches the current backlog at write time.
- Use `git diff --check` before claiming completion.
- If implementation grows beyond docs/process files, expand verification to the repo-wide checks required by `AGENTS.md`.

***REMOVED******REMOVED******REMOVED*** Task 1: Create The Operator Playbook

**Files:**
- Create: `docs/engineering/issue-triage.md`
- Reference: `docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md`

- [ ] **Step 1: Define the docs contract**

The new playbook must contain these sections:

```markdown
***REMOVED*** Issue Triage
***REMOVED******REMOVED*** Decision Model
***REMOVED******REMOVED*** Research Order
***REMOVED******REMOVED*** Execution Lanes
***REMOVED******REMOVED*** DRY, SOLID, and Reuse
***REMOVED******REMOVED*** Session Checklist
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
***REMOVED*** Issue Triage

***REMOVED******REMOVED*** Decision Model
- Classify each issue by `scope`, `risk`, `SDK coverage`, and `reuse pressure`.

***REMOVED******REMOVED*** Research Order
1. `docs/engineering/sdk-registry.md`
2. current code usage
3. Context7 / official docs
4. broad web search only as fallback

***REMOVED******REMOVED*** Execution Lanes
***REMOVED******REMOVED******REMOVED*** Quick execution
- local change
- established contract
- narrow verification

***REMOVED******REMOVED******REMOVED*** Plan needed
- multi-file or runtime-sensitive work
- route through `@writing-plans`, then `@executing-plans`

***REMOVED******REMOVED******REMOVED*** Design first
- ambiguous structure or cross-boundary changes
- route through `@brainstorming` before planning

***REMOVED******REMOVED*** DRY, SOLID, and Reuse
- prefer local fixes when the abstraction is not yet stable
- extract only after shared shape is proven

***REMOVED******REMOVED*** Session Checklist
1. shortlist backlog candidates
2. inspect touched surfaces
3. run `@sdk-research` when SDK/framework behavior matters
4. choose one lane
5. start exactly one issue
```

Keep the prose concise. The playbook should summarize the approved spec, not duplicate every paragraph.

- [ ] **Step 4: Run the docs check**

Run: `rg -n "^***REMOVED******REMOVED*** (Decision Model|Research Order|Execution Lanes|DRY, SOLID, and Reuse|Session Checklist)$|@sdk-research|@brainstorming|@writing-plans|@executing-plans|Context7|docs/engineering/sdk-registry.md" docs/engineering/issue-triage.md`

Expected: matches for all five headings and all required references.

- [ ] **Step 5: Commit**

```bash
git add docs/engineering/issue-triage.md
git commit -m "docs: add issue triage operator playbook"
```

***REMOVED******REMOVED******REMOVED*** Task 2: Codify The Workflow In Root Repo Guidance

**Files:**
- Modify: `AGENTS.md`
- Reference: `docs/engineering/issue-triage.md`
- Reference: `docs/superpowers/specs/2026-04-01-issue-triage-workflow-design.md`

- [ ] **Step 1: Define the failing check**

`AGENTS.md` must reference the new playbook and must name the three execution lanes directly:

```markdown
***REMOVED******REMOVED*** Issue Triage Workflow
- Before starting a new issue, classify it as `Quick execution`, `Plan needed`, or `Design first`.
- Use `docs/engineering/issue-triage.md` as the operator playbook.
```

- [ ] **Step 2: Run the pre-change check**

Run: `rg -n "Issue Triage Workflow|docs/engineering/issue-triage.md|Quick execution|Plan needed|Design first" AGENTS.md`

Expected: no match for `Issue Triage Workflow` or `docs/engineering/issue-triage.md`.

- [ ] **Step 3: Write the minimal implementation**

Add a short section to `AGENTS.md` near the workflow/process guidance with content shaped like:

```markdown
***REMOVED******REMOVED*** Issue Triage Workflow
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

***REMOVED******REMOVED******REMOVED*** Task 3: Publish A Dated Backlog Snapshot

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
***REMOVED*** 2026-04-01 Open Issues Triage Snapshot

Source command:
`gh issue list --state open --limit 30 --json number,title,labels,assignees,updatedAt,url`

***REMOVED******REMOVED*** Quick execution
- ***REMOVED***1075 ...

***REMOVED******REMOVED*** Plan needed
- ***REMOVED***1071 ...

***REMOVED******REMOVED*** Design first
- ***REMOVED***1070 ...

***REMOVED******REMOVED*** Needs discovery / defer
- ***REMOVED***1072 ...
```

- [ ] **Step 2: Run the precondition check**

Run: `test -f docs/plans/2026-04-01-open-issues-triage-snapshot.md`

Expected: exit code `1` because the dated snapshot does not exist yet.

- [ ] **Step 3: Write the minimal implementation**

Create `docs/plans/2026-04-01-open-issues-triage-snapshot.md` using the issues already agreed in the design:

```markdown
***REMOVED******REMOVED*** Quick execution
- ***REMOVED***1075
- ***REMOVED***1076
- ***REMOVED***1078
- ***REMOVED***1079

***REMOVED******REMOVED*** Plan needed
- ***REMOVED***1071
- ***REMOVED***1073
- ***REMOVED***1074
- ***REMOVED***1080
- ***REMOVED***1081
- ***REMOVED***1082
- ***REMOVED***1083

***REMOVED******REMOVED*** Design first
- ***REMOVED***1070
```

For everything not explicitly classified in the approved design, place it under `Needs discovery / defer` rather than inventing certainty.

- [ ] **Step 4: Re-run the backlog command and verify the snapshot**

Run: `gh issue list --state open --limit 30 --json number,title,labels,assignees,updatedAt,url`

Expected: the returned issue set still contains `***REMOVED***1070`, `***REMOVED***1071`, `***REMOVED***1073`, `***REMOVED***1074`, `***REMOVED***1075`, `***REMOVED***1076`, `***REMOVED***1078`, `***REMOVED***1079`, `***REMOVED***1080`, `***REMOVED***1081`, `***REMOVED***1082`, and `***REMOVED***1083`. If the backlog changed materially, refresh the snapshot before committing.

Run: `rg -n "***REMOVED***1070|***REMOVED***1071|***REMOVED***1073|***REMOVED***1074|***REMOVED***1075|***REMOVED***1076|***REMOVED***1078|***REMOVED***1079|***REMOVED***1080|***REMOVED***1081|***REMOVED***1082|***REMOVED***1083|Needs discovery / defer" docs/plans/2026-04-01-open-issues-triage-snapshot.md`

Expected: matches for all agreed issue IDs plus the defer bucket heading.

- [ ] **Step 5: Commit**

```bash
git add docs/plans/2026-04-01-open-issues-triage-snapshot.md
git commit -m "docs: add dated open issues triage snapshot"
```

***REMOVED******REMOVED******REMOVED*** Task 4: Verify Cross-References And Finish Cleanly

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

***REMOVED******REMOVED*** Guardrails

- Do not let the implementation drift into fixing any of the backlog issues themselves.
- Do not automate triage labels or issue updates in this plan; prove the manual workflow first.
- Keep `AGENTS.md` concise; detailed operating instructions belong in `docs/engineering/issue-triage.md`.
- Treat the dated snapshot as disposable evidence, not as timeless source of truth.
- Before claiming completion, apply `@verification-before-completion` thinking even though this is docs-only work.
