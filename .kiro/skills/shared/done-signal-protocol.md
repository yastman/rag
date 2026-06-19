# Shared: DONE-signal & route-marker protocol

> Single source of truth for the worker→orchestrator wake-up. Referenced by the
> swarm phase skills instead of being restated in each (#2305 P2).

## Wake-up line

A worker finishes by writing its Markdown report to `{{REPORT_FILE}}` (the
launcher substitutes the absolute canonical path), then writing its one-word
terminal status to `{{STATUS_FILE}}`:

```bash
# 1. write the full Markdown report
#    (your report tool / editor → {{REPORT_FILE}})
# 2. record the terminal status (exactly one word: DONE | FAILED | BLOCKED)
printf 'DONE\n' > "{{STATUS_FILE}}"
```

The launcher wrapper is the **sole wake-up channel**. After the agent's
`kiro-cli` session exits, the wrapper reads `{{STATUS_FILE}}` (falling back to
report-file existence) and sends exactly one terminal line to the orchestrator:

```text
[DONE] worker-name logs/REPORT.worker-name.md
[FAILED] worker-name logs/REPORT.worker-name.md
[BLOCKED] worker-name logs/REPORT.worker-name.md
```

**Workers must NOT run `tmux send-keys` themselves (#2820).** The old contract
asked the agent to self-send the wake-up line. When an agent *printed* that line
as chat text instead of executing it, the printed text landed in the worker log
and tripped the wrapper's grep-based reconcile into a false positive —
suppressing the failsafe so the orchestrator was never woken. Writing a status
**file** (which an agent does reliably, and whose printed echo cannot forge a
rail signal) removes the failure mode. A worker that only writes its report and
exits is still delivered correctly: the wrapper infers `DONE` from the non-empty
report file.

Do not print or summarize wake-up / tmux commands as final chat text.


## Route identity

- `ORCH_TARGET` is `session:@window-id` — an immutable tmux window-id target,
  never a `%pane` id and never a window *name* (the name can drift; the id can't).
- Refresh / verify the marker with
  `./scripts/set_orchestrator_window.sh --ensure-window-name <task>` from the
  intended orchestrator window. The marker lives in
  `.signals/orchestrator-window.json`. The script anchors on `$TMUX_PANE`
  (#2820), so it claims the window where the orchestrator process actually runs
  — not whatever window happens to be active when a subprocess invokes it.
- Do not use `C-j` to submit (it inserts a newline in the the orchestrator TUI); use a
  literal send + `C-m`.

## Report path convention

The canonical report path is `logs/REPORT.<worker>.md`. Launch metadata
(`REPORT_FILE`) and acceptance path-validation agree on this pattern; a wake-up
whose path does not match assigned `REPORT_FILE` is an `artifact_trust` event.
