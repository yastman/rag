---
name: swarm-acceptance
description: Accept tmux/Kiro worker terminal events. Use when a worker emits DONE/FAILED/BLOCKED, when acceptance must classify next action from a compact report, or when repair/relaunch routing is required. Markdown reports are default; strict JSON only for legacy .json terminal artifacts.
---

# Swarm Acceptance

Accept terminal worker artifacts without redoing worker execution.

## Default Contract

Run acceptance as a mandatory gate after `[DONE]`, `[FAILED]`, or `[BLOCKED]`.
Do not continue swarm flow without this pass.

Markdown is the default terminal artifact:

```text
[DONE] worker-name logs/REPORT.worker.md
[FAILED] worker-name logs/REPORT.worker.md
[BLOCKED] worker-name logs/REPORT.worker.md
```

Read Markdown reports and classify from compact artifact fields. Do not redo
worker task work locally. Do not run legacy JSON helpers, registry helpers, or
wake-up receipt checks for Markdown reports.

Use legacy machine-JSON acceptance only when terminal path ends in `.json` or
the user explicitly requests legacy artifact processing.

For automatic pipelines, advance by artifact control fields. Do not re-plan
from prose. Route to `$swarm-plan` only when `plan_revision_required: true` or
verified facts invalidate the accepted plan.

## Markdown Acceptance

1. Extract the wake-up line from the terminal event:
   `[DONE|FAILED|BLOCKED] <worker-name> <report-path>`.
2. **Validate the report path before reading**:
   a. The path must start with `logs/` and must not contain `..`, `/../`,
      or be an absolute path (unless `logs/` is always absolute in this repo).
   b. For code-changing workers, the report path must match the prompt-assigned
      `REPORT_FILE` from the worker launch contract when that metadata is
      available. Accept `logs/REPORT.<worker>.md` patterns; reject paths like
      `REPORT_FILE=/tmp/bad.md` or `../../etc/report.md`.
   c. If the wake-up line's report path does not match the prompt-assigned
      `REPORT_FILE` and launch metadata is available, return
      `failure_class: artifact_trust`, `decision: blocked`, and
      route to `$swarm-recovery`. Do not read a path that violates step 2a even
      if it is listed in the wake-up line.
3. Confirm the report path exists and is a file.
4. Check path size before reading. For large files, read bounded ranges only.
5. Read the report and classify the result:
   - read-only/research/intake/forensics/advisory: decide from the report;
   - code-changing: require worker-produced changed-files and verification
     evidence; route missing or contradictory proof to a verification/review
     worker instead of checking locally;
   - PR review: require worker-produced PR head and review decision evidence;
     route uncertainty to `$swarm-pr-review-flow`;
   - blocked/failed: decide relaunch, recovery, or ask user.
   for advisory/preflight reports, prefer these control fields when present:
   - `gate_result: pass | change_required | blocked`
   - `plan_revision_required: true | false`
   - `next_skill`
6. **Artifact-trust cross-check for advisory/preflight reports**:
   When the accepted `SWARM_PLAN` includes expected preflight gate expectations
   (e.g., a worker was launched as a read-only gate), cross-check the
   worker-authored control fields against the plan:
   - Do not accept `gate_result: pass` unless the plan assigned a preflight
     gate role to this worker. If no preflight gate was expected and the
     worker self-reports a gate result, treat it as `artifact_trust` with
     `decision: needs_review`.
   - Cross-check `next_skill` against the plan's expected follow-up worker
     phase. A worker that unilaterally sets `next_skill: swarm-plan` when the
     plan expects `next_skill: swarm-launch` is an `artifact_trust` mismatch.
   - If `plan_revision_required: true` is set without a `gate_result:
     change_required` or `gate_result: blocked`, treat as contradictory and
     return `needs_review`.
   - When launch metadata (WORKER_NAME, REPORT_FILE, ORCH_TARGET) is
     available from the prompt or plan, cross-check the wake-up line identity
     against it. A wake-up with a different WORKER_NAME than expected is
     `artifact_trust`. A wake-up that targets a different ORCH_TARGET than
     expected is `artifact_trust`, though detection requires comparing the
     actual wake-up target with the known orchestrator window.
7. Treat worker self-report as a lead, not proof. Accepted proof must be present
   in worker artifacts or a dedicated verification/review worker artifact.
   The orchestrator may only do mechanical control-plane checks: artifact path existence,
   file size, terminal event shape, and whether required report fields are
   present. Do not run `git`, `gh`, test, repo-scan, or code-inspection commands
   for content verification in acceptance.
   - for code-changing reports, require `changed_files`, `tests_run`,
     `verification_evidence`, and `evidence_commands`; missing or empty
     verification fields are a `needs_fix` or `needs_review` result, not an
     accepted result
   - for code-changing reports tagged as issue bugfix, duplicate, recurrence,
     umbrella, or containing a `Bug class`, require `anti_regression_evidence`
     with `classification`, bug class/canonical issue when applicable,
     guardrail evidence, and issue disposition.
     For classification `duplicate|recurrence|umbrella` or any `Bug class`, also
     require `bug_class_registry_evidence`; missing or contradictory evidence is a
     pre-disposition failure (`needs_fix` or `needs_review`).
     Prefer worker-produced evidence; when PR metadata/diff is available, use
     `scripts/ci/validate_pr_guardrails.py` as the bounded canonical check
     before disposition.
     Do not run broad repository scans for this decision; check only scoped
     files/fields (e.g., `.github/bug-classes.yml`, `changed_files`, `PR body`
     fields). Treat `docs/engineering/bug-classes.md` as a human mirror only;
     it is not sufficient registry evidence by itself.
     Missing evidence is a review blocker: return `needs_review`, set
     `failure_class: review_blocker`, route to `$swarm-pr-review-flow`, and list
     the missing evidence in `verified_facts`
   - contradictory or high-risk evidence routes to a verification/review worker,
     `$swarm-pr-review-flow`, `$swarm-recovery`, or `ask_user` by risk class
8. P0, security-sensitive, destructive, production, secret-store, SSH, cloud,
   or live-write work requires a separate review gate and explicit manual
   approval before destructive operations or final acceptance. Without that
   proof, return `needs_review` or `ask_user`.
9. If a Markdown report exists but no `[DONE]`, `[FAILED]`, or `[BLOCKED]`
   wake-up arrived, classify it as a worker/agent contract failure. Accept the
   report only if the user provides the DONE line or the artifact is otherwise
   sufficient, then relaunch or patch the worker skill/agent before reusing that
   route.
10. Disallow broad continuation after acceptance. No SSH, environment/server/log/
    storage archaeology, broad file scans, or unrelated replanning from prose.
    Route those tasks to `swarm-recovery`, `forensics`, or the owner worker.
11. **[MANDATORY]** Close the worker window after the report is processed. For Markdown
    reports, close by the exact worker/window name from the DONE line:

    ```bash
    python3 "scripts/close_markdown_worker_window.py" \
      "worker-name" --missing-ok
    ```

    This helper refuses orchestrator-like names and kills only an exact tmux
    window-name match. If the window is already missing, continue.
    Do NOT skip this step — unclosed windows accumulate and pollute the session.

## Disposition

After accepting code-changing work, choose one explicit disposition:

- `pr`: leave the worker worktree and branch intact, create or update the PR,
  report branch/head SHA/PR URL, and do not delete anything.
- `merge_done`: execute the merge, then clean up. Steps:
  1. Confirm required GitHub checks are green: `gh pr checks <pr> --required`
  2. Merge: `gh pr merge <pr> --merge --delete-branch`
  3. Fetch and verify merged head: `git fetch origin dev && git log origin/dev --oneline -1`
  4. Remove the worker worktree: `git worktree remove <worktree_path> --force`
  5. Delete the local branch if still present: `git branch -D <target_branch>`
  Never run `merge_done` if required checks are red or `merge_ready` is false.
  The `worktree_path` must be the path from `SWARM_PLAN.workers[].worktree`
  (e.g. `.worktrees/fix/2305-worker-a`), not the main repo checkout.
- `keep_worktree`: leave worktree and branch intact, record reason and next
  owner/action.
- `discard_with_confirmation`: require explicit human confirmation naming the
  exact worktree and branch; archive `git -C <worktree> diff` first; then remove
  only the confirmed worktree/branch.

Never delete or discard a dirty worktree without explicit confirmation.

## Same-Worker Follow-Up

Allow a same-worker follow-up only when all conditions are true:

- Worker pane/window is still alive and identified by worker/window name only
  (`worker-name`, not `%pane`).
- Follow-up remains in the same task scope with no ownership conflict.
- No production, secret-store, or live-write-risk operations are introduced.
- Follow-up writes a fresh compact artifact such as
  `FOLLOWUP.<task>.<timestamp>.md`.
- Send the follow-up to that same worker's unique tmux window target, such as
  `session:worker-window-name`; do not use `%pane` as route identity.
- The follow-up prompt must tell the worker to wake the orchestrator through
  its resolved `ORCH_TARGET=session:unique-orchestrator-window` after writing
  the fresh artifact.

## Repair Loop

For `needs_fix`, `needs_review`, `blocked`, and `failed`, record attempt budget
before relaunch or same-worker follow-up:

- `attempt`: current repair attempt number for this worker/report scope.
- `max_attempts`: default 2 for code-changing repair loops unless accepted plan
  states a smaller value.
- `failure_class`: report_schema | verification_failed | review_blocker |
  prompt_or_skill_drift | launcher_or_tmux | artifact_trust | scope_unclear.

Allowed repair routes:

- `report_schema`: one same-worker follow-up may request a fresh compact report
  with missing fields fixed; repeated schema failure routes to
  `$swarm-feedback-maintenance`.
- `verification_failed` or `review_blocker`: write a bounded review-fix prompt
  with exact failing evidence, allowed files, required Superpowers, validation
  commands, fresh report path, and retry count; then route to `$swarm-launch`.
  For missing anti-regression evidence, prefer `$swarm-pr-review-flow` before
  relaunch so the PR/issue disposition chain is reviewed against the current
  head.
- `launcher_or_tmux` or `artifact_trust`: route to `$swarm-recovery`.
- `prompt_or_skill_drift`: route to `$swarm-feedback-maintenance`.
- `scope_unclear`: ask the user.

Never exceed `max_attempts` silently. On repeated failure, return `escalate`,
`ask_user`, `$swarm-recovery`, or `$swarm-feedback-maintenance` by
`failure_class`.

## Legacy Machine JSON

For old `.json` terminal artifacts, use compact legacy helper output if needed.
Do not print full JSON in transcript; use summary plus direct fact checks.

## Output

Produce `ACCEPTANCE_DECISION` with:

- `decision`: accepted | needs_fix | needs_review | blocked | escalate | ask_user
- `artifact`: Markdown report path or legacy JSON signal path
- `verified_facts`
- `disposition`
- `required_followup`
- `next_action`
- `next_skill`

Emit `next_skill` only when another swarm phase is actually needed. Otherwise
report the accepted result to the user. Do not emit `next_skill:"swarm-plan"`
after SDK/docs/runtime advisory acceptance unless `plan_revision_required:
true` or verification invalidated the current plan.
