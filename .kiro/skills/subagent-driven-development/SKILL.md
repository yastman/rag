---
name: subagent-driven-development
description: Use when executing an implementation plan with independent tasks in the current session. Dispatches a fresh subagent per task with two-stage review (spec compliance, then code quality) after each task.
---

# Subagent-Driven Development

Execute a plan by dispatching a fresh subagent per task, with two-stage review after each.

**Core principle:** Fresh subagent per task + spec review + quality review = high quality, fast iteration.

## When To Use

- You have an implementation plan with mostly independent tasks.
- You want to stay in the current session (vs. handing off to parallel sessions).
- Tasks can be done sequentially without shared state conflicts.

## The Process

### Per-task cycle:

```
1. Extract task text and context from the plan
2. Dispatch implementer subagent (via subagent tool)
   → implements, tests, commits, self-reviews
   → reports: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
3. If NEEDS_CONTEXT → provide context, re-dispatch
4. If BLOCKED → assess and re-dispatch with more capable model or break task
5. Dispatch spec-reviewer subagent
   → confirms code matches spec
   → if issues found: implementer fixes → re-review
6. Dispatch code-quality-reviewer subagent
   → approves or requests fixes
   → if issues found: implementer fixes → re-review
7. Mark task complete
```

### After all tasks:

```
8. Dispatch final code reviewer for entire implementation
9. Run verification-before-completion
```

## Dispatch via subagent Tool

```
subagent(
  task="Implement task N: hook installation",
  stages=[
    { name="implement", role="kiro_default", prompt_template="<implementer prompt>" },
    { name="spec-review", role="kiro_default", depends_on=["implement"], prompt_template="<spec reviewer prompt>" },
    { name="quality-review", role="kiro_default", depends_on=["spec-review"], prompt_template="<quality reviewer prompt>" }
  ]
)
```

## Implementer Prompt Template

```
You are implementing Task N: [task name]

## Task Description
[FULL TEXT of task from plan — paste it, don't make subagent read file]

## Context
[Where this fits, dependencies, architectural context]

## Before You Begin
If you have questions about requirements, approach, or dependencies — ask them now.

## Your Job
1. Implement exactly what the task specifies
2. Write tests (TDD when specified)
3. Verify implementation works
4. Commit your work
5. Self-review
6. Report back

Work from: [directory]

## Self-Review Checklist
- Did I fully implement everything in the spec?
- Are names clear and accurate?
- Did I avoid overbuilding (YAGNI)?
- Do tests verify behavior (not just mock it)?

## Report Format
- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- What you implemented
- Test results
- Files changed
- Self-review findings
```

## Spec Reviewer Prompt Template

```
Review the implementation of Task N: [task name]

## Spec
[FULL TEXT of task spec]

## What Was Implemented
[Implementer's summary from their report]

## Your Job
Check ONLY spec compliance:
- Is everything from the spec implemented?
- Is anything implemented that wasn't in the spec?
- Are acceptance criteria met?

Output:
- ✅ SPEC_COMPLIANT or ❌ SPEC_ISSUES
- List of missing/extra items (if any)
```

## Code Quality Reviewer Prompt Template

```
Review code quality for Task N: [task name]

## Changes
[Files changed, commit SHA]

## Your Job
Check ONLY code quality:
- Names are clear and accurate
- No unnecessary complexity
- Tests verify behavior
- Follows existing patterns

Output:
- ✅ QUALITY_APPROVED or ❌ QUALITY_ISSUES
- List of issues (if any), classified as: Critical | Important | Minor
```

## Handling Implementer Status

| Status | Action |
|---|---|
| `DONE` | Proceed to spec review |
| `DONE_WITH_CONCERNS` | Read concerns, address if correctness issue, then review |
| `NEEDS_CONTEXT` | Provide missing context, re-dispatch |
| `BLOCKED` | Assess: more context → re-dispatch; too complex → break task; plan wrong → escalate |

## Rules

- **Never** dispatch multiple implementer subagents in parallel (file conflicts).
- **Never** skip reviews (spec compliance OR code quality).
- **Always** run spec review before quality review.
- **Always** re-review after fixes — don't accept "close enough".
- **Always** set up isolated git worktree before starting (use `using-git-worktrees` skill).

## Integration

Before starting: use `writing-plans` skill to create the plan this executes.  
After all tasks: use `finishing-a-development-branch` skill.  
Each implementer subagent should follow `test-driven-development` skill.
