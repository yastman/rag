***REMOVED*** AI Context Template

Use this template for storing session context in GitHub issues.

***REMOVED******REMOVED*** Full Template

```markdown
<!-- AI-CONTEXT:START -->
***REMOVED******REMOVED*** AI Session Context
_Last updated: YYYY-MM-DD HH:MM_

***REMOVED******REMOVED******REMOVED*** Status
**IN_PROGRESS** | **DONE** | **BLOCKED**

***REMOVED******REMOVED******REMOVED*** Progress
- [x] Completed item
- [ ] Pending item

***REMOVED******REMOVED******REMOVED*** Key Files
- `path/file.ts:45-78` — description
- `path/other.ts:120` — description

***REMOVED******REMOVED******REMOVED*** Decisions
- **Decision**: Reasoning/WHY

***REMOVED******REMOVED******REMOVED*** Blockers
_None_ or list blockers

***REMOVED******REMOVED******REMOVED*** Next Steps
1. First action
2. Second action

***REMOVED******REMOVED******REMOVED*** Resume Context
Brief summary for quick pickup by next session.
<!-- AI-CONTEXT:END -->
```

***REMOVED******REMOVED*** Minimal Template

For quick context saves:

```markdown
<!-- AI-CONTEXT:START -->
***REMOVED******REMOVED*** Context | IN_PROGRESS
**Files:** `file.py:45`, `other.py:120`
**Done:** task1, task2
**Next:** next task
**Resume:** One-line summary for cold start
<!-- AI-CONTEXT:END -->
```

***REMOVED******REMOVED*** Example: Real Context

```markdown
<!-- AI-CONTEXT:START -->
***REMOVED******REMOVED*** AI Session Context
_Last updated: 2026-01-07 15:30_

***REMOVED******REMOVED******REMOVED*** Status
**IN_PROGRESS**

***REMOVED******REMOVED******REMOVED*** Progress
- [x] Analyzed current bot flow
- [x] Reviewed reference implementation
- [ ] Create simplified flow diagram
- [ ] Implement changes

***REMOVED******REMOVED******REMOVED*** Key Files
- `handlers/start.py:45-78` — current start handler
- `data/config.yaml` — configuration
- `handlers/payment.py:120` — payment flow

***REMOVED******REMOVED******REMOVED*** Decisions
- **Remove intermediate steps**: Go directly to payment after selection (reduces friction)
- **Reference**: Competitor's 3-step flow is ideal

***REMOVED******REMOVED******REMOVED*** Blockers
_None_

***REMOVED******REMOVED******REMOVED*** Next Steps
1. Draw new flow diagram
2. Simplify handlers/start.py
3. Test with staging

***REMOVED******REMOVED******REMOVED*** Resume Context
Task: simplify flow, restore conversions.
Reference: competitor's simple flow.
Done: analysis of current state.
Next: create new flow diagram.
<!-- AI-CONTEXT:END -->
```

***REMOVED******REMOVED*** Tips

| Section | Purpose |
|---------|---------|
| Status | Quick visual scan — IN_PROGRESS/DONE/BLOCKED |
| Progress | Checklist of tasks |
| Key Files | `file:line` format for quick navigation |
| Decisions | WHY not WHAT — reasoning matters |
| Blockers | What's stopping progress |
| Next Steps | Concrete actions |
| Resume Context | Cold start summary — minimum to continue |
