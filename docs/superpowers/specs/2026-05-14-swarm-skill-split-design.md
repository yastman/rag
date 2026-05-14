# Swarm Skill Split Design

Date: 2026-05-14
Status: Draft for user review
Scope: Codex swarm skills, OpenCode worker agents, and worker-facing OpenCode skills

## Problem

`tmux-swarm-orchestration` has become a large mixed-responsibility skill. It
documents routing, issue intake, decomposition, tmux launch mechanics, worker
contracts, signal validation, PR review, review-fix, SDK gates, red flags, and
recovery. Even though it says the orchestrator should be thin, the skill still
tempts Codex to spend expensive context on broad research and analysis.

The desired model is stricter: the orchestrator should work through workers.
Workers should read issue/PR bodies, inspect code, draft decomposition, prepare
prompts, review diffs, validate artifacts, and return compact machine-checkable
artifacts. The orchestrator should keep only the important decisions.

## Goals

- Reduce orchestrator token use by moving broad discovery and analysis to
  OpenCode workers.
- Split the current large skill into small Codex skills with one responsibility
  each.
- Keep `tmux-swarm-orchestration` as a tiny router instead of a full workflow
  manual.
- Make worker outputs artifact-first so Codex can accept or reject them without
  repeating the worker's research.
- Make secretary workers the default intake path for issue, PR, queue, and
  artifact research.
- Preserve current model routing:
  - GPT-5.5 Codex decides.
  - DeepSeek V4 Flash prepares.
  - DeepSeek V4 Pro analyzes risks and reviews.
  - Kimi K2.6 implements.

## Non-Goals

- Do not let workers launch other workers directly.
- Do not make OpenCode workers decide merge/no-merge, production access,
  product tradeoffs, or safety exceptions.
- Do not remove visible tmux OpenCode sessions as the delivery runner.
- Do not require workers for tiny local edits or one-command answers.
- Do not create a large number of OpenCode agents before a repeated need is
  proven.

## Control-Plane Boundary

The orchestrator owns decisions, not bulk work.

Orchestrator responsibilities:

- choose the next route;
- launch workers and enforce active worker limits;
- enforce file reservations and sequential waves;
- validate artifact schema, launch metadata, model route, and command evidence;
- accept, reject, or escalate worker artifacts;
- ask the user for product, access, safety, or production decisions;
- decide final PR/task readiness and merge/no-merge;
- stop on red flags.

Worker responsibilities:

- inspect GitHub issues, PRs, comments, checks, and labels;
- inspect code and docs within the prompt's boundaries;
- produce decomposition and file reservation recommendations;
- draft next-worker prompts;
- run focused checks;
- implement code, tests, and docs;
- review PRs and fix named blockers;
- validate signals, plans, and artifacts;
- write compact JSON plus short Markdown evidence.

Core invariant:

```text
If a step requires broad reading, launch a worker. Codex reads accepted
artifacts, validator output, and short evidence summaries, not raw source
archaeology.
```

## Proposed Codex Skills

### `tmux-swarm-orchestration`

Keep this as a router only. It should fit in roughly 60-100 lines and point to
the next skill based on the current event or artifact.

Routes:

- no accepted intake artifact -> `swarm-intake`;
- accepted intake but no decomposition -> `swarm-plan`;
- ready worker prompt and reservations -> `swarm-launch`;
- worker DONE/FAILED/BLOCKED wake-up -> `swarm-acceptance`;
- PR review/review-fix/merge-readiness loop -> `swarm-pr-review-flow`;
- routing, registry, invalid JSON, stuck worker, or log leak -> `swarm-recovery`.

It should keep only repo-wide swarm invariants: secretary-first, no broad raw
reads by Codex, artifacts over transcripts, active worker cap, file reservation
rules, and production/secrets safety.

### `swarm-intake`

Purpose: perform first-pass issue, PR, queue, or artifact intake through
secretary workers.

Default route:

```text
secretary-flash / opencode-go/deepseek-v4-flash
```

Escalation route:

```text
secretary-pro / opencode-go/deepseek-v4-pro
```

Input:

- user request;
- optional issue number, PR number, queue instruction, artifact path, or status
  request.

Output:

- `SECRETARY_BRIEF.json`;
- `logs/SECRETARY.md`;
- optional `logs/NEXT_WORKER_PROMPT.md`.

Rules:

- Do not run raw `gh issue view`, `gh pr view`, broad `rg`, raw logs, or large
  source reads in Codex for routine intake.
- Launch `secretary-flash` unless the request is tiny/local or an accepted
  brief already exists.
- Launch `secretary-pro` only when Flash reports low confidence, high risk,
  SDK/runtime uncertainty, conflicting artifacts, or unresolved decomposition.
- Stop after accepted intake. Recommend the next skill instead of silently
  moving into implementation.

### `swarm-plan`

Purpose: convert an accepted intake artifact into an execution plan.

Input:

- accepted `SECRETARY_BRIEF.json`;
- optional `logs/NEXT_WORKER_PROMPT.md`.

Output:

- `SWARM_PLAN.json`;
- optional worker prompt drafts.

Allowed routes:

- no worker;
- one worker;
- sequential waves;
- parallel waves;
- planner-first;
- review-only;
- blocked.

Rules:

- If decomposition requires broad code reading, launch a planning secretary
  worker instead of doing it in Codex.
- Reserve files before implementation launch.
- Make each worker slice disjoint when using parallel waves.
- Include focused checks and docs impact expectations in each slice.

### `swarm-launch`

Purpose: own only tmux, worktree, registry, prompt validation, and launcher
mechanics.

Input:

- accepted `SWARM_PLAN.json` or explicit launch request;
- worker prompt file;
- reservations;
- selected OpenCode agent/model/skills.

Output:

- `LAUNCH_RECORD.json`;
- registry entry;
- launch metadata path.

Rules:

- Do not study issues, diffs, logs, or PRs.
- Run prompt validators before full worker launches.
- Ensure selected OpenCode agent frontmatter model matches `OPENCODE_MODEL`.
- Validate `SWARM_LOCAL_ONLY=1` agent restrictions before launch.
- Require route-check nonce when routing is ambiguous.

### `swarm-acceptance`

Purpose: process worker terminal states.

Input:

- DONE/FAILED/BLOCKED wake-up;
- signal JSON;
- launch metadata;
- registry entry.

Output:

- `ACCEPTANCE_DECISION.json`.

Rules:

- Validate schema, prompt SHA, worker route, branch/base, reserved files,
  command evidence, docs impact, and bug disposition.
- Do not redo semantic review if a current-head PR review artifact exists.
- Launch artifact-check or review workers when validation needs broad evidence.
- Close worker tmux windows after terminal state processing.

### `swarm-pr-review-flow`

Purpose: own PR review, review-fix, re-review, and merge-readiness routing.

Input:

- PR number or accepted worker DONE artifact with PR URL;
- current head SHA;
- accepted review or review-fix artifacts.

Output:

- `MERGE_READINESS.json`.

Rules:

- Runtime/code PRs need a read-only `pr-review` worker on the current head SHA.
- Review workers are read-only.
- Fixes go to `pr-review-fix` workers with named blockers only.
- After each review-fix wave, launch a fresh review worker.
- The orchestrator decides merge/no-merge from accepted artifacts.

### `swarm-recovery`

Purpose: handle broken orchestration state.

Input:

- invalid signal;
- stale registry;
- missing or wrong route marker;
- stuck worker;
- massive log leak;
- contradictory artifacts.

Output:

- `RECOVERY_REPORT.json`;
- repaired marker/registry only when safe.

Rules:

- Read raw OpenCode logs only when artifacts and targeted status checks are
  insufficient.
- Prefer `stat`, validator output, registry state, and short pane captures.
- Stop normal orchestration until recovery has a clear disposition.

## OpenCode Worker Plane

### Agents

Keep or create these tracked repo agents in `.opencode/agents/`:

- `secretary-flash.md`: DeepSeek V4 Flash, default cheap intake and prompt
  drafting.
- `secretary-pro.md`: DeepSeek V4 Pro, escalation for complex decomposition,
  SDK/runtime baseline, and conflicting artifacts.
- `pr-worker.md`: Kimi K2.6 implementation route.
- `pr-review.md`: DeepSeek V4 Pro read-only PR review.
- `pr-review-fix.md`: DeepSeek V4 Pro named-blocker fix route.
- `complex-escalation.md`: DeepSeek V4 Pro escalation analysis.

All default local-only agents should satisfy launcher checks:

```yaml
permission:
  webfetch: deny
  websearch: deny
  external_directory: ask
mcp:
  context7:
    enabled: false
  exa:
    enabled: false
```

Context7 or external docs access should be selected explicitly through a
different route or prompt policy, not available by accident.

### Worker-Facing OpenCode Skills

Keep existing worker skills:

- `swarm-pr-finish`;
- `swarm-review-fix`;
- `swarm-bug-reporting`;
- `project-docs-maintenance`;
- repo `.opencode/skills/gh-pr-review`.

Create one new worker-facing skill first:

```text
swarm-secretary-intake
```

Purpose:

- tell secretary workers how to produce `SECRETARY_BRIEF.json`;
- define allowed bounded reads;
- define forbidden actions;
- define `recommended_route`;
- require compact evidence and prompt-draft artifacts.

Do not create `swarm-plan-draft`, `swarm-artifact-check`, or
`swarm-runtime-verify` until repeated use proves the need. Those can start as
prompt patterns or references.

## Artifact Pipeline

The intended artifact flow is:

```text
SECRETARY_BRIEF.json
  -> SWARM_PLAN.json
  -> LAUNCH_RECORD.json
  -> worker DONE/FAILED/BLOCKED JSON
  -> ACCEPTANCE_DECISION.json
  -> MERGE_READINESS.json when PR flow applies
```

Each artifact should include:

- producing worker/agent/model;
- input artifact paths;
- confidence or decision;
- evidence commands;
- risks;
- needed user/orchestrator decisions;
- next recommended skill or worker route.

The orchestrator should reject artifacts that are not compact enough to verify
without rerunning the worker's broad research.

## Skill Creation Plan

Use `skill-creator` for new Codex skills:

1. Run `init_skill.py` for each new Codex skill under
   `${CODEX_HOME:-$HOME/.codex}/skills`.
2. Keep each `SKILL.md` body short and imperative.
3. Put long schemas and prompt templates in one-level `references/` files only
   when they are reusable.
4. Generate `agents/openai.yaml` for each skill with deterministic
   `display_name`, `short_description`, and `default_prompt`.
5. Run `quick_validate.py` on each created skill.

Suggested Codex skill resources:

- `swarm-intake/references/secretary-brief-schema.md`;
- `swarm-plan/references/swarm-plan-schema.md`;
- `swarm-launch/references/launch-checklist.md`;
- `swarm-acceptance/references/acceptance-checklist.md`;
- `swarm-pr-review-flow/references/review-loop.md`;
- `swarm-recovery/references/recovery-checklist.md`.

Avoid copying full old reference files into every new skill. Move only the
minimum reusable contract into each skill and leave the old package as the
temporary source during migration.

## Migration Plan

Phase 1: Thin intake and agents

- Track `secretary-flash.md` and `secretary-pro.md`.
- Add OpenCode `swarm-secretary-intake`.
- Create Codex `swarm-intake`.
- Add a router pointer from `tmux-swarm-orchestration` to `swarm-intake`.
- Validate secretary signals and prompt snippets.

Phase 2: Split launch and acceptance

- Create `swarm-launch`.
- Create `swarm-acceptance`.
- Move launcher and signal-validation instructions out of the router.
- Keep scripts in the existing `tmux-swarm-orchestration/scripts/` directory
  until there is a reason to physically move them.

Phase 3: Split planning and PR review flow

- Create `swarm-plan`.
- Create `swarm-pr-review-flow`.
- Move decomposition and review-loop policy into those skills.
- Keep `swarm-worker-contract` as the shared worker DONE contract.

Phase 4: Recovery and cleanup

- Create `swarm-recovery`.
- Reduce `tmux-swarm-orchestration/SKILL.md` to router size.
- Archive or delete old duplicated references only after all new skills have
  validation coverage.

## Validation

Required validation:

```bash
python3 /home/USER/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /home/USER/.codex/skills/swarm-intake
python3 /home/USER/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /home/USER/.codex/skills/swarm-plan
python3 /home/USER/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /home/USER/.codex/skills/swarm-launch
python3 /home/USER/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /home/USER/.codex/skills/swarm-acceptance
python3 /home/USER/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /home/USER/.codex/skills/swarm-pr-review-flow
python3 /home/USER/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  /home/USER/.codex/skills/swarm-recovery
```

Swarm package validation:

```bash
python3 -m pytest /home/USER/.codex/skills/tmux-swarm-orchestration/tests -q
```

Repo validation for tracked OpenCode files:

```bash
git diff --check -- .opencode docs/superpowers/specs
opencode agent list | rg "secretary-flash|secretary-pro|pr-worker|pr-review|pr-review-fix|complex-escalation"
```

Manual forward test after implementation:

- invoke `swarm-intake` on one real issue and confirm Codex does not read raw
  issue/PR bodies before the secretary artifact exists;
- validate the secretary signal;
- route to `swarm-plan` from the accepted brief;
- launch one no-edit artifact-check or prompt-draft worker before trying a code
  worker.

## Risks

- Too many skills can make routing harder. Mitigation: keep
  `tmux-swarm-orchestration` as the visible router and make each new skill
  artifact-driven.
- Workers may return verbose artifacts. Mitigation: reject artifacts that are
  not compact and machine-checkable.
- Secretary workers may overreach into implementation. Mitigation: put
  forbidden actions in both agent files and `swarm-secretary-intake`.
- OpenCode local/global skill discovery can drift. Mitigation: prefer tracked
  repo agents and globally installed worker skills, and make launcher metadata
  report exact skill paths.
- Existing references may duplicate new skills during migration. Mitigation:
  phase the split and remove old duplicated text only after validation passes.

## Open Questions

- Should `swarm-intake` always stop after `SECRETARY_BRIEF`, or may it invoke
  `swarm-plan` automatically for high-confidence briefs?
- Should `swarm-secretary-intake` live globally in
  `~/.config/opencode/skills` or be tracked in repo `.opencode/skills`?
- Should `swarm-plan` produce implementation prompts itself, or always ask a
  planning secretary worker to draft them?
