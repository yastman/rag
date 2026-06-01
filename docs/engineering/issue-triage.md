# Issue Triage

## Decision Model
- Classify each issue by `scope` (blast radius), `risk` (critical invariant or runtime impact), `SDK coverage` (existing feature fit), and `reuse pressure` (whether shared structure is stable enough to extract).
- `Quick execution` fits narrow, established changes with concrete verification.
- `Plan needed` fits multi-file or runtime-sensitive work that needs explicit sequencing.
- `Design first` fits structurally ambiguous changes, cross-boundary changes, or contract shifts.

## Research Order
1. Read `docs/engineering/sdk-registry.md`.
2. Check current code usage in the repository.
3. Use Context7 or official docs for version-sensitive behavior.
4. Use broad web search only as a fallback.

## Execution Lanes
### Quick execution
- Keep the blast radius local and follow existing repository patterns.
- Prefer the smallest sufficient verification for the touched surface.

### Plan needed
- Use this for multi-file, refactor, dependency, or runtime-impacting work.
- Route through `@writing-plans`, then execute with `@executing-plans`.

### Design first
- Use this when structure, ownership, or contracts are still ambiguous.
- Route through `@brainstorming`, write a short spec, get user review, then plan.

## Duplicate and Recurring Bugs
- **Duplicate**: same symptom, scenario, and root cause as an existing issue, with
  no new evidence. Close it with the canonical issue link.
- **Recurrence**: same bug class with new evidence, environment, path, or failure
  mode. Keep it actionable, link the canonical bug class, and add or strengthen
  the guardrail before closing.
- **Umbrella**: broad parent issue that owns multiple child issues or a cluster
  map. Close it only after child issues and verification are resolved.
- **New bug**: no matching root cause or registered bug class. Triage normally.

For any duplicate or recurrence, record:

```text
Type: duplicate | recurrence | umbrella | new
Canonical issue:
Related issues:
Bug class:
Missing or weak guardrail:
Verification:
```

Root cause is defined by the failing contract boundary, not by title wording.
Examples: "BGE-M3 service is unreachable because the Compose port contract is
wrong" and "Langfuse trace context is lost across raw executor boundaries" are
root causes. If a recurrence is confirmed, update
the source registry [`.github/bug-classes.yml`](../../.github/bug-classes.yml)
or the human mirror [`docs/engineering/bug-classes.md`](bug-classes.md), or explain why the existing
guardrail already covers it.

## DRY, SOLID, and Reuse
- Prefer local fixes when the shared shape is still evolving.
- Extract shared logic only after the repeated shape is stable and clearly reduces change risk.
- Run `@sdk-research` when SDK or framework behavior may replace custom code.
- Use SOLID ideas only when they improve testability, replaceability, or safety for the current issue.

## Session Checklist
1. Pick the current backlog candidate to classify.
2. Inspect touched surfaces and likely blast radius.
3. Run SDK-first research with `docs/engineering/sdk-registry.md`, local code, and Context7 as needed.
4. Choose exactly one lane: `Quick execution`, `Plan needed`, or `Design first`.
5. Record the lane decision before implementation starts.
