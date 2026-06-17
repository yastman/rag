---
name: swarm-session-forensics
description: Use when investigating a concrete tmux/Kiro swarm session, window, pane, raw log, signal folder, or transcript; launches or accepts Markdown-first forensics reports and uses strict JSON only for explicit legacy machine handoff.
---

# Swarm Session Forensics

Investigate one concrete swarm session through a bounded worker so the orchestrator gets a
compact Markdown explanation instead of reading raw logs in the orchestrator
context.

Same-worker follow-up is a bounded lifecycle action (single-session continuity),
not a default mode for transcript archaeology.

## Default Contract

For normal questions such as "what happened", "where did tokens go", "why did
routing fail", or "why did the worker misunderstand", require a Markdown report:

```text
logs/SESSION_FORENSICS.<task>.md
```

The terminal event is:

```text
[DONE] worker-name logs/SESSION_FORENSICS.<task>.md
```

Do not require secretary JSON, trace JSON, token JSON, wake-up receipts, or
`accept_worker_signal.py` for human/the orchestrator-consumed forensics.

## Workflow

### Same-Worker Follow-up

Use this mode only when all conditions hold:

- Same task scope as the active session.
- The same worker is still live in its pane/window (verify via tmux state).
- No ownership boundary or safety restriction is crossed.
- The investigation is bounded to the same worker's lifecycle window.

If allowed, spin the worker with a new compact artifact and wake-up event (not raw
log reads), then ask for completion in Markdown with a fresh
`SESSION_FORENSICS.<task>.<suffix>.md` artifact.

1. Resolve the concrete target with narrow checks only: named window, pane,
   signal path, log path, transcript path, or today's session directory.
2. Preserve route identity by checking `ORCH_TARGET session:unique-window-name`;
   treat pane IDs as transient debug metadata, never as identity.
3. Prefer compact evidence checks first: report artifact, bounded tmux window/pane
   status checks, and the compact report fields.
4. Read raw logs/transcripts/pane captures only if the compact artifact is missing,
   unreadable, or materially contradictory, and then only in a bounded, capped
   window.
5. Ask the worker to write a compact report under 120 lines with:
   `scope`, `target`, `question`, `confidence`, `timeline`, `root_cause`,
   `bloat_points`, `instruction_conflicts`, `recommended_fixes`,
   `needs_user`, `evidence_paths`, and `evidence_commands`.
6. After DONE, read the Markdown report and decide whether to report, patch a
   skill, launch recovery, or ask the user.
7. Escalate to `secretary-pro` only when the target spans multiple sessions,
   evidence conflicts remain after follow-up, safety/production ambiguity exists,
   or Flash reports low confidence.

## Output

Produce or accept a Markdown `SESSION_FORENSICS` report. Emit
`next_skill:"swarm-feedback-maintenance"` only when a reusable skill/helper fix
is needed. Emit `next_skill:"swarm-recovery"` only when runtime state is unsafe.
