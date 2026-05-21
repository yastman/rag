# Event-Driven Worker Wait for the Swarm Orchestrator

Reference for the orchestrator (Codex/Kiro) and worker launchers so the
wait-for-worker phase consumes near-zero context tokens. Tracks issue
[#1275](https://github.com/yastman/rag/issues/1275).

## The Problem

The historical wait loop runs in the orchestrator's turn:

```text
while not done:
    sleep
    find .signals/
    git status
```

Every iteration spends tool-call budget even when nothing changed. Long
worker tasks encourage repeated "still waiting" checks. If the user
interrupts the turn, background worker state becomes hard to track.

## The Contract

The orchestrator should not poll. After launching workers it should:

1. Persist `.signals/active-workers.jsonl` with one JSON line per worker:

   ```json
   {
     "worker": "W-name",
     "signal_file": "/abs/path/.signals/worker-W-name.json",
     "heartbeat_file": "/abs/path/.signals/heartbeat-W-name.json",
     "branch": "kiro/<n>-<slug>",
     "base": "dev",
     "started_at": "2026-05-21T11:00:00Z",
     "tmux_window": "swarm:W-name",
     "pane_pid": 12345,
     "prompt_sha256": "..."
   }
   ```

2. Tell the user that workers are running and end the turn.

The orchestrator resumes only when:

- A worker writes its terminal signal JSON and wakes the orchestrator
  via the canonical tmux send-keys form pinned by issue
  [#1721](https://github.com/yastman/rag/issues/1721) and the contract
  test [`tests/contract/test_tmux_send_keys_pattern_contract.py`](../../tests/contract/test_tmux_send_keys_pattern_contract.py):

  ```bash
  tmux send-keys -t "$ORCH_TARGET" -l "[DONE] $WORKER_NAME $REPORT_FILE"
  sleep 0.25
  tmux send-keys -t "$ORCH_TARGET" C-m
  ```

  The repo ships the user-runnable fixer
  [`scripts/swarm_fix_send_keys_pattern.py`](../../scripts/swarm_fix_send_keys_pattern.py)
  to migrate any legacy launcher that still uses the broken trailing
  `Enter` form.

- The user explicitly asks for status. In that case the orchestrator
  reads a single compact JSON snapshot via the watchdog (below) and
  reports — without scanning files manually.

## The Watchdog

[`scripts/swarm_watchdog.py`](../../scripts/swarm_watchdog.py) is a
read-only watchdog that produces that snapshot. One call returns one
JSON document covering every active worker, derived from
`.signals/active-workers.jsonl` plus each worker's signal/heartbeat
artifacts.

### One-shot mode (default)

```bash
python scripts/swarm_watchdog.py --once \
  --registry .signals/active-workers.jsonl
```

Output (single JSON line plus an optional `[ALL_DONE]` marker):

```text
{"timestamp": "2026-05-21T16:36:58Z",
 "signals_dir": ".signals",
 "registry": ".signals/active-workers.jsonl",
 "workers": [
   {"worker": "W-alpha", "phase": "done",  "signal_exists": true,  "heartbeat_age_s": null},
   {"worker": "W-beta",  "phase": "active","signal_exists": false, "heartbeat_age_s": 12.3}
 ]}
```

The orchestrator reads one line, parses one JSON, and decides — no
filesystem walk, no `git status`, no per-worker `cat`.

The `[ALL_DONE]` marker on its own line is intentional: a tmux watcher
pane can grep for it without parsing JSON. When every active worker has
reached a terminal phase, the marker is printed.

### Watch mode

For sidecar tmux panes that should wake the orchestrator on transition:

```bash
python scripts/swarm_watchdog.py --watch \
  --interval 5 \
  --timeout 1800 \
  --registry .signals/active-workers.jsonl
```

The script polls every `--interval` seconds and exits 0 when either
`[ALL_DONE]` or `[TIMEOUT]` is reached. Combine with tmux send-keys to
notify the orchestrator pane when state changes.

### Reported phases

| Phase | Meaning |
|---|---|
| `active` | Registered, no terminal signal, heartbeat (if any) is fresh. |
| `done` | Signal JSON status is `done`. |
| `failed` | Signal JSON status is `failed`, **or** the signal file exists but is corrupt (`error` field set). |
| `blocked` | Signal JSON status is `blocked`. |
| `stale` | No terminal signal yet, heartbeat older than `--stale-threshold` seconds (default 600). Investigate before resuming. |

Terminal status from the signal JSON always wins over heartbeat
liveness: a `done` worker is `done` even if its heartbeat went stale
(common when the worker exited cleanly without one last heartbeat
write).

## Worker Heartbeat Format

Optional, recommended for tasks expected to run longer than ~5 minutes.
The worker writes `~/.signals/heartbeat-W-name.json` periodically:

```json
{
  "worker": "W-name",
  "phase": "editing|testing|creating_pr|blocked",
  "last_artifact": "tests/unit/test_x.py",
  "updated_at": "2026-05-21T11:42:00Z"
}
```

The watchdog uses **mtime** of the file as the heartbeat age, so the
worker can either rewrite the file in full or `touch` it. The `phase`
and `last_artifact` fields are diagnostic — Codex reads them only when
the user asks for status.

## Worker-Side Wake-Up Etiquette

After writing the authoritative signal JSON, a worker may send a
single-line tmux pointer to the orchestrator pane:

```bash
tmux send-keys -t "$ORCH_TARGET" -l "[DONE] W-name /abs/path/.signals/worker-W-name.json"
sleep 0.25
tmux send-keys -t "$ORCH_TARGET" C-m
```

Allowed transition pointers (one line, no logs/diffs/long summaries):

```text
[DONE]    W-name /abs/path/.signals/worker-W-name.json
[FAILED]  W-name /abs/path/.signals/worker-W-name.json
[BLOCKED] W-name /abs/path/.signals/worker-W-name.json
[STATUS]  W-name /abs/path/.signals/heartbeat-W-name.json
```

Rules:

- The JSON artifact is the **truth**. The tmux pointer is just a hint.
- Codex validates the pointer against `.signals/active-workers.jsonl`,
  reserved files, branch/base, prompt checksum, and PR metadata before
  accepting it. A stray pointer that doesn't match a registered worker
  is ignored.
- Use only the four transition pointers above, not chatty progress.

## Verification

The watchdog contract is pinned by 17 unit tests in
[`tests/unit/scripts/test_swarm_watchdog.py`](../../tests/unit/scripts/test_swarm_watchdog.py)
covering registry parsing (incl. malformed JSONL), per-worker
inspection (active / terminal status / stale heartbeat / corrupt
signal), the full snapshot, and CLI behaviour (`--once` modes,
`[ALL_DONE]` marker emission).

Run from the repo root:

```bash
uv run pytest tests/unit/scripts/test_swarm_watchdog.py -q
```

The send-keys wake-up form is enforced by
[`tests/contract/test_tmux_send_keys_pattern_contract.py`](../../tests/contract/test_tmux_send_keys_pattern_contract.py)
(refs #1721, #1590).

## Maintainer Steps (out of repo)

The user-level swarm-orchestration skills under
`~/.codex/skills/tmux-swarm-orchestration/` and
`~/.config/opencode/skills/swarm-*/` should:

1. Document the event-driven wait policy: launch workers, persist the
   active-workers registry, end the turn.
2. Resume only on a tmux wake-up pointer or an explicit user status
   request.
3. Use `python scripts/swarm_watchdog.py --once` to read worker state
   instead of scanning `.signals/` manually.
4. (Optional) Run `python scripts/swarm_watchdog.py --watch` in a
   sidecar tmux pane and wire its `[ALL_DONE]` line to a wake-up
   send-keys back to the orchestrator pane.

These external-skill changes are tracked in
[`docs/superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md`](../superpowers/plans/2026-05-20-swarm-superpowers-worker-policy-external-changes.md)
and remain a maintainer task — the autonomous repo PR cannot edit
files outside the repository.
