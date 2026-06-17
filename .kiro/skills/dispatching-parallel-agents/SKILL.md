---
name: dispatching-parallel-agents
description: Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies. Dispatch one subagent per independent problem domain and let them work concurrently via the subagent tool.
---

# Dispatching Parallel Agents

Delegate independent tasks to specialized subagents with isolated context.

**Core principle:** One subagent per independent problem domain. Let them work concurrently.

## When To Use

**Use when:**
- 2+ test files or subsystems failing with different root causes.
- Multiple independent features or tasks with no shared state.
- Each problem can be understood without context from others.

**Don't use when:**
- Failures are related (fixing one might fix others).
- Agents would edit the same files.
- You don't yet know what's broken — investigate first.

## The Pattern

### 1. Identify Independent Domains

Group work by what's broken or what's being built:
- Problem A: isolated to file/subsystem X
- Problem B: isolated to file/subsystem Y
- Problem C: isolated to file/subsystem Z

### 2. Dispatch via subagent Tool

Use the `subagent` tool with a `blocking` stage per independent domain:

```
subagent(
  task="Fix 3 independent test failures",
  stages=[
    { name="fix-abort", role="kiro_default", prompt_template="Fix agent-tool-abort.test.ts..." },
    { name="fix-batch", role="kiro_default", prompt_template="Fix batch-completion.test.ts..." },
    { name="fix-race",  role="kiro_default", prompt_template="Fix race-conditions.test.ts..." }
  ]
)
```

Stages with no `depends_on` start immediately in parallel.

### 3. Craft Focused Agent Prompts

Each prompt must be:
- **Self-contained** — include all context needed, do not rely on session history.
- **Specific scope** — one test file, one subsystem, one problem.
- **Clear constraints** — "Do NOT change production code" or "Fix tests only".
- **Explicit output** — "Return: summary of root cause and changes made".

Good prompt template:
```
Fix the 3 failing tests in src/agents/agent-tool-abort.test.ts:

1. "should abort tool with partial output capture" - expects 'interrupted at' in message
2. "should handle mixed completed and aborted tools" - fast tool aborted instead of completed
3. "should properly track pendingToolCount" - expects 3 results but gets 0

These are timing/race condition issues. Your task:
1. Read the test file and understand what each test verifies
2. Identify root cause
3. Fix by replacing arbitrary timeouts with event-based waiting
4. Do NOT increase timeouts — find the real issue
5. Do NOT change other files

Return: Summary of root cause and exactly what you changed.
```

### 4. Review and Integrate

When all agents return:
1. Read each summary.
2. Verify fixes don't conflict (no edits to same files).
3. Run full test suite.
4. Integrate if no conflicts.

## Common Mistakes

| Wrong | Right |
|---|---|
| "Fix all the tests" (too broad) | "Fix agent-tool-abort.test.ts" (focused) |
| No error context | Paste the error messages and test names |
| No constraints | "Do NOT change production code" |
| Vague output | "Return summary of root cause and changes" |

## Sequential vs Parallel

Use `depends_on` when a stage needs results from a prior stage:

```
stages=[
  { name="investigate", ... },
  { name="fix", depends_on=["investigate"], ... },
  { name="verify", depends_on=["fix"], ... }
]
```

## Review Loop Pattern

Use `loop_to` for review → fix cycles:

```
stages=[
  { name="implement", role="kiro_default", ... },
  { name="review", role="kiro_default", loop_to={target="implement", trigger="NEEDS_CHANGES", max_iterations=3}, ... }
]
```
