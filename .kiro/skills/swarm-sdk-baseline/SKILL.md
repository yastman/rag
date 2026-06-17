---
name: swarm-sdk-baseline
description: Use before launching implementation when SDK/API/runtime uncertainty exists; produces Markdown SDK advisory by default and strict machine gates only when explicitly required before automated launch.
---

# Swarm SDK Baseline

Prevent custom work that duplicates repo-native or SDK-native capabilities.

## Default Contract

Default output is a Markdown advisory:

```text
logs/SDK_ADVISORY.<task>.md
```

Use it when the orchestrator/human will read the recommendation before deciding whether to
launch implementation. Do not require JSON for advisory research.

## When To Use

Use as a read-only preflight worker skill when a `SWARM_PLAN` gate says a task
touches SDK/API/framework/runtime behavior and an implementation worker would
otherwise need open-ended research.

Do not use for typo fixes, comments, formatting-only changes, docs-only prose,
or one-file mechanical edits without SDK/API/runtime behavior.

Normal automatic pipelines do not route `swarm-plan -> swarm-sdk-baseline ->
swarm-plan` by default. `swarm-plan` records the gate, `swarm-launch` launches
this advisory worker, and planning repeats only if the advisory explicitly says
`plan_revision_required: true`.

## Workflow

1. Classify the slice: `not_applicable`, `sdk_sensitive`, or `inconclusive`.
2. If `not_applicable`, record that in the plan; no worker is needed.
3. If research is needed, run as one read-only worker launched by
   `$swarm-launch` with `KIRO_REQUIRED_SKILLS=swarm-sdk-baseline` and write
   a Markdown advisory.
4. Worker reads local docs/current code first using the indexed-tool contract
   in `shared/indexed-tool-contract.md` (Code Indexer first, CodeGraph for exact
   source-backed symbol bodies, `rg`/`find` fallback only; native freshness via
   `codeindexer jobs` / `doctor` / `doctor --fix`, no custom git hooks).
5. Use Context7 only for named library/API freshness questions.
6. The advisory must state whether the existing plan may continue, needs a
   plan revision, or is blocked.

## Markdown Advisory Shape

```markdown
# SDK_ADVISORY
classification:
confidence:
local_docs_status:
local_pattern:
context7_evidence:
recommended_shape:
forbidden_custom:
allowed_custom:
docs_update_required:
implementation_recommendation:
gate_result: pass | change_required | blocked
plan_revision_required: true | false
blocked_workers:
next_skill:
secret_policy:
evidence_commands:
```

## Legacy Strict Gate

Use strict `SDK_DOCS_BASELINE` JSON only when an automated launch must consume
the result without the orchestrator interpretation. Mark the prompt and launcher with
`SWARM_CONTRACT=strict_json`.

## Output

Produce or accept Markdown `SDK_ADVISORY`. Emit `next_skill:"swarm-launch"`
when `gate_result: pass` and the current accepted plan can continue. Emit
`next_skill:"swarm-plan"` only when `plan_revision_required: true`. Emit
`next_skill:"ask_user"` or leave the pipeline blocked when the advisory cannot
choose a safe implementation shape.
