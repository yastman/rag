# Shared: DONE-signal & route-marker protocol

> Single source of truth for the worker→orchestrator wake-up. Referenced by the
> swarm phase skills instead of being restated in each (#2305 P2).

## Wake-up line

A worker finishes by writing its Markdown report, then waking the orchestrator
with exactly one terminal line:

```text
[DONE] worker-name logs/REPORT.worker.md
[FAILED] worker-name logs/REPORT.worker.md
[BLOCKED] worker-name logs/REPORT.worker.md
```

Send it through the resolved orchestrator window only:

```bash
tmux send-keys -t "$ORCH_TARGET" -l "[DONE] $WORKER_NAME $REPORT_FILE"
sleep 0.25
tmux send-keys -t "$ORCH_TARGET" C-m
```

Do not print or summarize the wake-up commands as final chat text.

## Route identity

- `ORCH_TARGET` is `session:@window-id` — an immutable tmux window-id target,
  never a `%pane` id and never a window *name* (the name can drift; the id can't).
- Refresh / verify the marker with
  `./scripts/set_orchestrator_window.sh --ensure-window-name <task>` from the
  intended orchestrator window. The marker lives in
  `.signals/orchestrator-window.json`.
- Do not use `C-j` to submit (it inserts a newline in the the orchestrator TUI); use a
  literal send + `C-m`.

## Report path convention

The canonical report path is `logs/REPORT.<worker>.md`. Launch metadata
(`REPORT_FILE`) and acceptance path-validation agree on this pattern; a wake-up
whose path does not match assigned `REPORT_FILE` is an `artifact_trust` event.
