---
name: swarm-recovery
description: 'Use when tmux swarm state is unsafe or inconsistent, or when a swarm artifact says next_skill:"swarm-recovery": broken orchestrator routing, stale registry, invalid signal JSON, stuck workers, missing wake-up, massive raw logs, wrong pane, or production/safety red flags.'
---

# Swarm Recovery

Diagnose broken swarm state with bounded reads, repair only the control surface,
and avoid turning recovery into broad task discovery.

## Worker-First Rule

The orchestrator is the control plane. If this step requires broad reading, launch or use
a worker artifact. Do not spend orchestrator context on raw issue archaeology,
full diffs, raw logs, broad repo scans, or transcript reading unless the
artifact is missing, contradictory, safety-critical, or the task is tiny.

## Handoff Discipline

If this skill emits `next_skill`, stop current-phase work and invoke that
skill before continuing. Do not perform the next phase locally unless the next
skill is unavailable or the task is tiny/local.

## Inputs

- The failing command, signal, launch record, registry entry, pane/window, or
  user status request.
- Existing `LAUNCH_RECORD`, signal path, and registry state when available.

## Workflow

1. Stop normal orchestration. Do not launch implementation/review workers while
   routing or artifact trust is broken.
2. Check active safety boundaries from the focused swarm skill that failed.
   Use archived legacy notes only when explicitly investigating historical
   tmux swarm behavior; do not make archive docs a normal
   recovery dependency.
3. Use targeted checks first: `stat`, `jq`, `registry_state.py`, signal
   validator output, launch metadata, and at most a short `tmux capture-pane`.
   Long-running workers are normal. Do not enter recovery merely because a
   worker is still running and has not produced `DONE/FAILED/BLOCKED`; only
   investigate after a timeout trigger, user status request, missing first
   artifact threshold, or contradictory launch/registry evidence.
4. Do not read raw `logs/*.kiro.log` unless launcher/TUI failure cannot be
   diagnosed from JSON artifacts. Check size first.
5. If route repair is needed, run
   `./scripts/set_orchestrator_window.sh --ensure-window-name <task>`
   from the intended the orchestrator orchestrator window. Do not manually
   `tmux rename-window` as a substitute for the helper.
6. When multiple live the orchestrator/node windows exist, perform an actual route-check:
   send a unique nonce to the resolved `ORCH_TARGET`, confirm it appeared in
   the intended orchestrator chat, then relaunch with
   `SWARM_ROUTE_CHECK_CONFIRMED=1` and `SWARM_ROUTE_CHECK_NONCE=<nonce>`. Do
   not treat marker/current-window evidence alone as nonce confirmation.
7. If JSON is invalid, ask the worker to rewrite the signal or launch a bounded
   artifact-check worker. Do not silently normalize invalid worker output.
8. If production, secrets, live CRM writes, SSH, cloud, DNS, or VPS access is
   implicated without explicit authorization, block and ask the user.

## Output

Produce `RECOVERY_REPORT` with:

- `problem`
- `evidence`
- `actions_taken`
- `state_after`
- `safe_to_continue`
- `required_user_decision`
- `next_action`
- `next_skill`
- `handoff_reason`

Emit `next_skill:"swarm-intake"`, `next_skill:"swarm-plan"`,
`next_skill:"swarm-launch"`, or `next_skill:"swarm-acceptance"` only when
`safe_to_continue:true`. Otherwise ask the user or stop.
