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
- Route through `@brainstorming` before planning.

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
