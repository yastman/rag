---
name: swarm-feedback-maintenance
description: "Use when the orchestrator must record, debug, and repair skill or swarm-system failures: bad skill triggers, missing handoffs, YAML/frontmatter bugs, context bloat, worker confusion, contract drift, invalid worker artifacts, stale tmux routing, launcher bugs, prompt drift, Kiro agent/skill drift, or repeated orchestration failure patterns."
---

# Swarm Feedback Maintenance

Turn user reports and real swarm failures into tracked, narrow fixes to skills,
Kiro agents, launcher contracts, prompts, validators, or tests.

## Core Rule

Record first, then fix. Treat feedback as evidence, not as a vague patch
request. Create or update a feedback journal entry before editing reusable
skill or swarm sources.

Use `$skill-creator` low-overhead update path for skill edits. Do not create
planning docs, new scripts, or broad tests unless the failure is recurring and
mechanically testable.

## Feedback Journals

Use one journal entry per failure. Keep active and resolved entries in separate
files so the orchestrator can triage current work without reading a large historical log.

| Failure scope | Active journal path | Resolved journal path |
| --- | --- | --- |
| Specific the orchestrator/Kiro skill bug | `~/.kiro/skill-feedback/<skill-name>.active.md` | `~/.kiro/skill-feedback/<skill-name>.resolved.md` |
| Swarm-wide launcher/tmux/signal/prompt/worker failure | `~/.kiro/swarm-feedback/<repo-or-system>.active.md` | `~/.kiro/swarm-feedback/<repo-or-system>.resolved.md` |

If an old single-file journal exists, do not read or rewrite it by default.
Append new `open`, `blocked`, and `needs_followup` entries to the active journal.
Append `fixed` and `false_alarm` entries to the resolved journal only when
closing an entry. Read the legacy file only when the user asks for migration or
when a specific old entry is needed.

Canonical lifecycle: an active bug starts as one `open` entry in the active
journal. Fix and validate it while it remains active. When the fix is complete,
remove that entry from the active journal and append the completed entry to the
resolved journal with `Status: fixed` or `Status: false_alarm`. Do not leave a
duplicate resolved item in the active journal.

Entry template:

```markdown
## YYYY-MM-DD - short title

Status: open|fixed|blocked|needs_followup
Skill/System: name
Severity: low|medium|high
Source: user_report|worker_artifact|test_failure|forward_test
Class: trigger_bug|handoff_bug|yaml_bug|context_bloat|contract_drift|worker_confusion|launcher_or_tmux|validation_gap|false_alarm

Problem:
Evidence:
Root cause:
Fix:
Validation:
Residual risk:
```

Do not paste secrets, production `.env`, tokens, private URLs, phone numbers,
or raw TUI log dumps into journals. Summarize sensitive evidence and cite local
artifact paths.

## Workflow

1. **Capture**
   - Identify the affected skill/system and journal path.
   - Append an `open` entry to the active journal with the user's report and
     any artifact paths.
   - If the report is about an obvious single skill edit with enough evidence
     in the chat, continue locally.
   - If discovery is broad, unclear, or swarm-run specific, launch
     `secretary-flash` to produce a compact evidence dossier before the orchestrator reads
     broad artifacts.

2. **Classify**
   - `trigger_bug`: frontmatter description does not cause correct invocation.
   - `handoff_bug`: skill fails to emit or obey `next_skill`.
   - `yaml_bug`: invalid frontmatter or metadata.
   - `context_bloat`: skill causes unnecessary broad reads or token spend.
   - `contract_drift`: artifact schema, worker report, command evidence, docs
     impact, or reserved-files contract drifted.
   - `worker_confusion`: Kiro worker misunderstands required behavior.
   - `launcher_or_tmux`: stale pane, wrong route, registry, prompt SHA,
     permission, TUI, or wake-up failure.
   - `validation_gap`: failure should be caught by quick validation, tests, or
     prompt/signal validators.
   - `false_alarm`: evidence shows the report is outdated or already fixed.

3. **Patch**
   - Edit the reusable source of truth, not one historical prompt or transcript.
   - For Kiro skill behavior, patch `~/.kiro/skills/*/SKILL.md`.
   - For Kiro worker behavior, patch `.kiro/skills/*/SKILL.md`
     or repo `.kiro/skills/*/SKILL.md`.
   - For model/tool permissions, patch `~/.kiro/agents/*.json` or repo
     `.kiro/agents/*.md`.
   - For repeated schema/prompt failures, patch validator/tests/snippets only
     when the check is deterministic and likely to catch recurrence.
- Keep the fix as small as possible. Do not bloat
     focused swarm skills; keep swarm skills lean
     package as legacy runtime support only.

4. **Validate**
   - Run
     `python3 "scripts/validate_worker_prompt.py" <skill-folder>`
     for changed skill folders.
   - Run focused tests when the changed package has tests, for example:
     ```bash
     uv run --no-sync pytest -q tests/contract/test_kiro_swarm_skills_contract.py
     ```
   - For Kiro agent routing changes, check `kiro-cli agent list` and the
     launcher-required fields when relevant.
   - Forward-test with a low-risk real tmux Kiro worker only when the
     change is broad, ambiguous, high-risk, or has already failed in real use.

5. **Close**
   - Update the active journal entry to `blocked` or `needs_followup` if work
     is still unfinished.
   - When an entry is `fixed` or `false_alarm`, move it from the active journal
     to the resolved journal instead of leaving a duplicate active copy.
   - The active journal should contain only unresolved work after close; the
     resolved journal should contain the final root cause, fix, validation, and
     residual risk for completed items.
   - Record root cause, files changed, validation commands, and residual risk.
   - If blocked, state the missing decision, artifact, access, or safety
     approval.

## Orchestrator Token Budget

The orchestrator should spend tokens on classification, patching, and validation, not
evidence archaeology.

Before a secretary/evidence artifact exists, the orchestrator may do only targeted checks:
current tmux pane, selected files named by the user, exact artifact paths,
selected skill frontmatter/body, and validator/test output.

Do not run broad `git status`, wide `find`, broad `rg`, raw GitHub issue/PR
archaeology, raw TUI log reads, full `.signals` listings, or archived session
search as routine intake. If those facts are needed, ask a secretary worker for
a compact dossier.

## Handoff

- For normal swarm task execution, start with `$swarm-intake` and then follow
  `next_skill` through focused swarm phase skills.
- For broken runtime state, use `$swarm-recovery`.
- For PR review/merge readiness, use `$swarm-pr-review-flow` or `$gh-pr-review`
  depending on whether the orchestrator or Kiro owns the review.
- For skill creation or focused skill edits, use `$skill-creator`.

If this skill emits `next_skill`, stop current-phase work and invoke that skill
before continuing.
