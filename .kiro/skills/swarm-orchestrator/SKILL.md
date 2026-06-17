---
name: swarm-orchestrator
description: Route tmux/Kiro swarm automation as the single control-plane entry point. Use when asked to start, continue, or execute swarm issue/PR/queue/backlog work, when an accepted swarm artifact needs next-step routing, or when a worker emits DONE/FAILED/BLOCKED. Route terminal events to $swarm-acceptance and keep the orchestrator out of worker execution.
---
> See full pipeline: `docs/designs/swarm-pipeline.md`


# Swarm Orchestrator

Route swarm work without doing worker work locally.

## Core Contract

Keep the orchestrator as the control plane. Route to focused swarm phases for intake,
planning, launch, acceptance, recovery, forensics, review flow, or feedback
maintenance.

Treat workers as execution owners for broad reading, discovery, implementation,
review, and report drafting.

All swarm phases and Kiro worker prompts must preserve the indexed-tool
contract in `shared/indexed-tool-contract.md`: Code Indexer MCP first for
broad/semantic discovery and compact symbol tracing, CodeGraph as the
source-backed companion for exact symbols, and `rg`/`find` only as fallback;
native `auto_reindex` freshness (no custom git hooks). When results look stale,
check `codeindexer jobs` / `codeindexer doctor` and repair with
`codeindexer doctor --fix` or a focused reindex before trusting results.

When this file says "invoke a phase skill", load and follow that phase
`SKILL.md` in the current turn, then stop this skill. Do not spawn the orchestrator
subagents for swarm worker execution.

The orchestrator may:

- classify the current request or terminal event;
- invoke one focused phase skill;
- launch or accept workers through that phase;
- read compact Markdown reports;
- run only mechanical control-plane checks such as exact artifact path
  existence/size, terminal event classification, and route-marker status.

The orchestrator must not do worker work locally; do not implement worker tasks directly
in this entry skill: no broad
archaeology, no broad repo scans, no raw TUI transcript digestion, no SDK
baseline research, no local implementation, and no edits to reserved worker files.

Do not use built-in `spawn_agent`, `send_input`, or `wait_agent` as the swarm
worker mechanism. Use tmux/Kiro workers launched by focused swarm phases,
primarily through:

`./scripts/launch_kiro_worker.sh`.

## Phase Skill Set

Use this routing vocabulary:

- `$swarm-intake`: first worker-backed issue/PR/queue/backlog/artifact intake.
- `$swarm-plan`: smart routing, decomposition, file reservations, worker
  allocation, preflight gates, and launchable `SWARM_PLAN`.
- `$swarm-launch`: mechanical tmux/Kiro launch, including preflight gate
  workers declared by the plan.
- `$swarm-acceptance`: process DONE/FAILED/BLOCKED Markdown reports and decide
  the next phase from artifact control fields; content verification belongs to
  verification/review workers.
- `$swarm-sdk-baseline`: read-only SDK/docs/runtime advisory skill used by
  preflight workers or fallback advisory routing, not the normal post-plan
  bounce.
- `$swarm-pr-review-flow`: review waves, review-fix waves, and merge-readiness.
- `$swarm-recovery`: broken tmux route, registry, wake-up, launcher, or
  artifact trust.
- `$swarm-session-forensics`: concrete worker/session/log/transcript
  investigation.
- `$swarm-feedback-maintenance`: reusable skill/helper/agent drift repair.

## Fast Routing

Pick exactly one next phase from the current state. Invoke it and stop this
skill. Do not force every task through every phase.

| Situation | Route |
| --- | --- |
| User asks to audit, repair, organize, or discuss swarm/orchestrator contracts, routing, worker prompts, Kiro skills, or swarm-system behavior | `$swarm-feedback-maintenance` |
| User reports reusable swarm skill/helper/agent drift or repeated orchestration failure | `$swarm-feedback-maintenance` |
| User asks for read-only issue/PR/queue/backlog summary or human-consumed planning | `$swarm-intake` |
| User explicitly invokes `$swarm-orchestrator`, `swarm`, or asks for swarm/worker automation tasks without repair/maintenance intent | `$swarm-intake` |
| User says start/execute/continue an issue, PR, queue, backlog, or artifact and no accepted compact brief is present | `$swarm-intake` |
| Accepted compact intake/forensics/advisory/review report exists and work needs routing | `$swarm-plan` |
| Accepted `SWARM_PLAN` is launch-ready | `$swarm-launch` |
| Worker sent `[DONE]`, `[FAILED]`, or `[BLOCKED]` with a Markdown report or legacy signal path | `$swarm-acceptance` |
| tmux route, launcher, registry, signal, wake-up, or artifact trust is broken | `$swarm-recovery` |
| A standalone advisory is requested, or no accepted plan exists but SDK/API/runtime uncertainty blocks planning | `$swarm-sdk-baseline` |
| User asks what happened in a concrete worker/session/log/transcript | `$swarm-session-forensics` |
| User asks for PR review waves, review-fix, or merge readiness through swarm | `$swarm-pr-review-flow` |

If multiple routes match, route to `$swarm-recovery` first when routing or
artifact trust is broken. Otherwise route worker DONE/FAILED/BLOCKED artifacts
to `$swarm-acceptance` first. For non-terminal user requests, repair,
maintenance, audit, and "наведи порядок" intent routes to
`$swarm-feedback-maintenance` before the generic explicit `$swarm-orchestrator`
or `swarm` route. Priority order: `recovery`, `acceptance`,
`feedback-maintenance`, `plan`, `launch`, `intake`. A terminal worker event
routes to `$swarm-acceptance` and is not a final stop unless artifact trust is
broken.

Use `no_worker` only for truly tiny non-discovery checks that need no issue/PR
metadata, repo scan, transcript reading, or report drafting.

## Auto-Pipeline Policy

When the user asks for automatic execution/continuation, keep routing phase to
phase until an acceptance-level stop condition appears. Continue from compact
control fields and worker-produced verification output, not local worker work.

For requests framed as "from idea/issue to PR", treat a created or updated PR
with accepted verification evidence as the requested endpoint. Do not treat
merge, deploy, production access, secret access, SSH/cloud access, or live CRM
writes as implied by "to PR"; those remain explicit manual-approval gates.

Terminal worker events route to `$swarm-acceptance`. Stop after `ACCEPTANCE_DECISION`
only when decision is `accepted`, `ask_user`, `escalate`, `blocked` without a
valid recovery route, or the requested endpoint is reached. Continue through
`next_skill` for `needs_fix`, `needs_review`, `plan_revision_required`, or
recovery-worthy outcomes.

Stop conditions:

- user approval is required for production, secrets, SSH, cloud, live CRM
  writes, or merge-to-`dev` if no explicit merge policy was given;
- a worker `[FAILED]`/`[BLOCKED]` decision is not acceptable after route/verification;
- an artifact sets `plan_revision_required: true`, which routes to
  `$swarm-plan`;
- required tests/checks fail after a code-changing worker;
- route, launcher, wake-up, or artifact trust is broken, which routes to
  `$swarm-recovery`;
- the requested endpoint is reached, such as a compact plan, launched workers,
  created or updated PR, merge-readiness report, or completed merge.

<!-- Guard blocks: Worker-First Rule, Handoff Discipline, Token Budget →
     see `shared/orchestrator-guard-blocks.md` -->

## Phase Rules

- Do not call direct `kiro-cli chat --no-interactive`, `--verbose`, raw log polling, or broad
  `rg/find` from this entry skill.
- Do not route swarm work to the orchestrator subagents. If worker execution is needed,
  route to `$swarm-intake`, `$swarm-plan`, `$swarm-launch`, or another focused
  swarm phase skill that owns tmux/Kiro worker launch or acceptance.
- For read-only human planning requests such as "изучи последние issues и
  составь план", route to `$swarm-intake`; the secretary worker drafts the
  compact plan and the orchestrator reports or routes from that artifact.
- Do not require strict JSON unless the user explicitly requests legacy
  `SWARM_CONTRACT=strict_json` or the terminal artifact is already JSON.
- Do not continue through several phases in prose. Invoke the next skill,
  follow that skill, and let each phase produce the next decision.
- Do not use this skill for ordinary non-swarm coding unless the user asks for
  workers, swarm, queue/issue automation, tmux/Kiro routing, or a swarm
  artifact names a swarm phase.
- If a request explicitly names `$swarm-orchestrator`, "swarm", or "worker
  automation", classify it as swarm work and route to a worker-backed phase
  unless the request is a truly tiny non-discovery control-plane check.
- Preserve unique-window worker routing by using stable worker-window/artifact
  identity (ORCH_TARGET/accepted report path) and never pane IDs.

## Output

Produce a compact routing decision with:

- `route`
- `reason`
- `phase_skill`
- `artifact_or_event`
- `orchestrator_local_checks`
- `next_action`

Then invoke `phase_skill` in the same the orchestrator session when the route is
worker-backed. Omit `phase_skill` only when the route is `no_worker` for a
truly tiny non-discovery control-plane check, or when the request is ordinary
non-swarm local work.

## External Community Skills

You are the brain of the swarm. You decide when to use external skills.
External skills are thinking tools, not mandatory bureaucracy.

| Skill | Use when |
|---|---|
| `grill-me` | Requirements vague, assumptions need pressure-testing, scope unclear before swarm-plan |
| `grill-with-docs` | Task changes codebase with CONTEXT.md / ADR / domain model — check plan against docs |
| `writing-plans` | Non-trivial task needs a plan (files, steps, tests, risks, done criteria) |
| `executing-plans` | Implementation worker executing an orchestrator-provided plan |
| `test-driven-development` | Behavior changes or regression risk exists |
| `using-git-worktrees` | Workers that modify files — verify correct worktree |
| `verification-before-completion` | Before any worker claims [DONE] — fresh verification required |
| `requesting-code-review` | Before launching PR review worker |
| `receiving-code-review` | When fixing review blockers |
| `finishing-a-development-branch` | Final checklist before PR/merge decision |

**Rules:**
- Do not allow any skill to launch nested swarm unless explicitly authorized
- Do not allow skills to override orchestrator decisions
- Skills must not merge PR
- Skills must not modify `.kiro/skills/**` or `.kiro/agents/**` unless task is explicitly about agent infrastructure
- Auto-merge policy: when the orchestrator is running in autonomous mode (user said "автономный режим", "делай всё", "авто режим", or equivalent) AND all review workers returned `merge_ready: true` with no blockers, the orchestrator MUST merge into `dev` automatically without waiting for additional confirmation. Manual confirmation is only required when: (a) merging to `main`/`master`, (b) any reviewer returned blockers, (c) the PR touches secrets/auth/destructive operations, or (d) the user did NOT grant autonomous mode.
- Reference-only skills (`.kiro/skills_reference/`) are installed by `scripts/install_ready_skills.sh` as upstream read-only copies for context; they are NOT activated. Kiro-only deployments do not need them at runtime — the active `.kiro/skills/` copies are canonical.
