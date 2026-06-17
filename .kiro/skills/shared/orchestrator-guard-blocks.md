# Shared: Orchestrator Guard Blocks

> Single source of truth for the three recurring orchestrator constraints.
> Phase skills reference this file instead of restating them inline.

## Worker-First Rule

The orchestrator is the control plane. If this step requires broad reading,
launch or use a worker artifact. Do not spend orchestrator context on raw issue
archaeology, full diffs, raw logs, broad repo scans, or transcript reading.
Safety-critical or tiny local tasks are the only exceptions. If artifacts are
missing or contradictory, launch a secretary worker to produce or verify them.

## Handoff Discipline

If this skill emits `next_skill`, stop current-phase work and invoke that skill
before continuing. Do not perform the next phase locally unless the next skill
is unavailable or the task is tiny/local.

## Token Budget

Before invoking the next phase, run only tiny targeted checks:

- exact artifact path existence or size;
- whether a terminal line is `[DONE]`, `[FAILED]`, or `[BLOCKED]`;
- whether the user already supplied an accepted compact report or plan;
- whether the current request is swarm automation or ordinary local work.

Do not use tiny checks as a pretext for SSH/VPS/server access, broad log
archaeology, storage scanning, or pane/pane-id driven routing. If answering
requires issue/PR/queue metadata, repo reading, synthesis, or report drafting,
route to a worker-backed phase.
