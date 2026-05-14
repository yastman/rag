# Swarm Wake-Up Helper Design

Date: 2026-05-13

## Goal

Replace hand-written tmux wake-up snippets in swarm worker prompts with one
canonical helper script. The helper should make worker completion notification
reliable when Codex is sleeping and should preserve the existing routing model:
workers notify the orchestrator through the unique tmux window name captured at
launch time.

The immediate problem is not signal JSON creation. The live smoke test showed
that a worker can write valid JSON but still fail to wake Codex if the tmux
submit key leaves `[DONE] ...` buffered in the orchestrator input. That delivery
logic should live in a tested script, not copied prompt prose.

## Current Context

The swarm launcher records these routing fields in launch metadata and prompt
placeholders:

- `ORCH_TARGET=session:orch-...`
- `ORCH_PANE=%N`
- `ORCH_WINDOW_ID=@N`
- `ORCH_WINDOW_NAME=orch-...`
- `ORCH_SESSION_NAME=session`
- `ORCH_WINDOW_INDEX=N`

The current design correctly treats `ORCH_TARGET` as the notification address.
The unique window name is more stable than pane focus and is already validated
by route-check nonce before ambiguous launches.

The fragile part is worker-side wake-up delivery. Today workers copy a bash
snippet that reads status, builds `[DONE]`, `[FAILED]`, or `[BLOCKED]`, runs
`tmux send-keys`, sleeps, and submits. Any prompt can drift from the canonical
sequence, and fixing submit behavior requires editing multiple docs and worker
skills.

## Options Considered

### Option A: Keep snippets, improve lint

Keep the current bash snippets in prompts and add stricter prompt validation.
This is low-effort, but it leaves the behavior duplicated and still asks the
model to generate terminal control logic correctly every time.

### Option B: Notification helper

Add a small script, for example `swarm_notify_orchestrator.py` or
`swarm_notify_orchestrator.sh`, that reads an existing signal JSON and sends the
tmux wake-up. Workers still own JSON creation, validation evidence, commits,
pushes, and PR metadata. The helper owns status-to-tag mapping, route guard
checks, tmux submit sequence, fallback, and a small receipt.

This is the recommended first step because it removes the fragile delivery
logic without expanding the signal JSON interface.

### Option C: Full signal helper

Add a larger script that both writes DONE/FAILED/BLOCKED JSON and wakes the
orchestrator. This would centralize more behavior, but it also forces a
complete JSON-builder interface for implementation, review, review-fix,
artifact-check, and docs workers. That is too much migration surface for the
current bug.

## Proposed Design

Implement Option B: a canonical notification helper under the
`tmux-swarm-orchestration` skill package:

```text
${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py
```

Workers call it after atomically writing `SIGNAL_FILE`:

```bash
python3 "${CODEX_HOME:-$HOME/.codex}/skills/tmux-swarm-orchestration/scripts/swarm_notify_orchestrator.py" \
  --signal "$SIGNAL_FILE" \
  --worker "$WORKER_NAME" \
  --target "$ORCH_TARGET" \
  --window-id "$ORCH_WINDOW_ID" \
  --window-name "$ORCH_WINDOW_NAME" \
  --session "$ORCH_SESSION_NAME" \
  --pane "$ORCH_PANE"
```

The script reads `status` from the signal JSON and maps:

- `done` -> `[DONE]`
- `failed` -> `[FAILED]`
- `blocked` -> `[BLOCKED]`

The script then verifies live tmux identity before sending anything:

- `tmux display-message -p -t "$ORCH_TARGET" '#{window_id}'` matches
  `--window-id`;
- `#{window_name}` matches `--window-name`;
- `#{session_name}` matches `--session`;
- optional `--pane` still belongs to the same `--window-id` if the pane exists.

If guards pass, the script sends:

```text
[TAG] WORKER SIGNAL_FILE
```

to `ORCH_TARGET` using the currently validated submit sequence: literal text,
short delay, `Enter`, short fallback delay, `C-j`.

The helper should create a receipt next to the signal file:

```text
.signals/wakeup-W-name.json
```

The receipt records worker, signal file, tag, target, guard identities,
submit sequence, fallback attempts, exit status, and timestamp. This gives the
orchestrator evidence without scraping raw TUI logs.

## Error Handling

The helper exits non-zero and does not send wake-up if:

- signal JSON is missing or invalid;
- `status` is absent or not `done|failed|blocked`;
- worker name is missing or mismatches the expected worker when that field
  exists in JSON;
- `ORCH_TARGET` is not a live tmux target;
- live target identity does not match launch-time window/session guards;
- optional pane guard points to a different window.

If the initial send sequence appears to leave text buffered, the helper may
perform one fallback using a named tmux buffer followed by the same
`Enter`/`C-j` submit sequence. The receipt must record whether fallback was
attempted. Detecting buffered text from outside a TUI is imperfect, so fallback
should be conservative and bounded.

## Integration Points

Update the canonical contracts to tell workers to call the helper instead of
copying tmux commands:

- `tmux-swarm-orchestration/references/signal-schema.md`
- `tmux-swarm-orchestration/infrastructure.md`
- `tmux-swarm-orchestration/worker-contract.md`
- OpenCode `swarm-pr-finish/SKILL.md`
- prompt snippets and worker-prompt references

The launcher should continue resolving placeholders into prompt files. It does
not need to invoke the helper directly because notification happens after the
worker has produced signal JSON.

## Testing

Add focused contract tests for the helper:

- valid `done|failed|blocked` status maps to the correct tag;
- invalid/missing JSON exits non-zero;
- tmux guard mismatch exits before sending;
- receipt JSON is written on success;
- command construction uses `ORCH_TARGET` and not stale pane focus;
- docs and OpenCode worker skill reference the helper path instead of raw
  `tmux send-keys` wake-up snippets.

Add one live smoke test after implementation:

1. launch a low-risk OpenCode worker in a fresh worktree;
2. have it write a minimal signal JSON;
3. have it invoke `swarm_notify_orchestrator.py`;
4. confirm `[DONE] W-name SIGNAL_FILE` appears as a submitted orchestrator chat
   event, not as buffered input;
5. confirm `wakeup-W-name.json` exists;
6. close the test worker window and remove the worktree.

## Migration Plan

Phase 1 introduces the helper and updates the reusable contracts. Existing
already-launched workers may still use old snippets; process their signal JSON
manually if their wake-up line remains buffered.

Phase 2 updates new prompt snippets so future workers call only the helper.
Prompt validation should reject newly authored full prompts that contain raw
terminal wake-up snippets unless they are explicitly testing the helper.

Phase 3 can consider a full signal JSON builder only if repeated JSON-shape
drift remains a separate problem. That should be a distinct design because it
changes worker artifact ownership, not just wake-up delivery.

## Non-Goals

- Do not replace unique window-name routing.
- Do not route by current tmux focus.
- Do not make workers re-read mutable `.signals/orchestrator-pane.json` after
  launch.
- Do not build full DONE JSON in this first helper.
- Do not introduce production, Docker, or network dependencies for wake-up.

## Open Questions

- Should the helper be Python for easier JSON/receipt handling, or Bash for
  simpler worker invocation? Python is recommended because JSON parsing and
  structured receipt writing are first-class.
- Should prompt validation reject all raw `tmux send-keys` wake-up snippets
  immediately, or only warn during the first migration pass?
