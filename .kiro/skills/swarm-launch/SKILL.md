---
name: swarm-launch
description: Launch accepted SWARM_PLAN workers through tmux/Kiro with SWARM_CONTRACT=markdown, validate preflight and KIRO_REQUIRED_SKILLS constraints, and enforce mandatory report fields, gates, and manual review requirements.
---

# Swarm Launch

Launch workers mechanically from an accepted `SWARM_PLAN`.

## Inputs

- Accepted `SWARM_PLAN` with worker allocations.
- Confirmed preflight instructions and report path expectations.
- Any open safety/manual-review constraints.

## Workflow

1. **Create worktrees before launch.** For every code-changing worker in the plan,
   run `scripts/create_worker_worktree.sh` to provision an isolated worktree
   and capture the real path:

   ```bash
   WORKTREE_PATH=$(bash scripts/create_worker_worktree.sh \
     "<target_branch>" "<base_branch>")
   # e.g. WORKTREE_PATH=$(bash scripts/create_worker_worktree.sh \
   #   fix/2305-worker-a dev)
   ```

   Pass the path as `WORKER_WORKTREE` when launching. Never run code-changing
   workers in the main repo checkout — they would share the same branch and
   could clobber each other.

   **HARD STOP: Do not call `launch_kiro_worker.sh` for a code-changing
   (implementation / review-fix / bug-debug) worker without first running
   `create_worker_worktree.sh` and setting `WORKER_WORKTREE`. Skipping this
   step is the #1 cause of branch-clobber bugs in parallel swarm runs.**

   Read-only / secretary / review (no file edits) workers do not need a worktree;
   omit `WORKER_WORKTREE` for them.

2. Validate each launchable worker before launch:
   - `git -C <worktree> status --short` has only expected noise.
   - `git -C <worktree> branch --show-current` is `target_branch`.
   - `target_branch` is based on the remote PR base, usually `origin/<base_branch>`;
     verify common history with the PR base before launch or before PR creation.
   - `reserved_files` are present and match the plan.
   - `KIRO_REQUIRED_SKILLS` includes all required worker role skills and required superpowers.
   - `SWARM_CONTRACT=markdown` is in payload.
   - `strict_json` is not used unless explicitly requested by user approval.
2. If preflight gates exist, launch only read-only gate workers first.
   - Require each advisory to include:
     - `gate_result: pass | change_required | blocked`
     - `plan_revision_required: true | false`
     - `blocked_workers: [...]`
     - `next_skill: swarm-launch | swarm-plan | ask_user`
   - On `pass`, continue with unblocked workers.
   - On `change_required`, stop and route to `swarm-plan`.
   - On `blocked`, stop and route to user approval or recovery.
3. Build each worker prompt with `WORKER_NAME`, `REPORT_FILE=logs/*.md`, and
   a plain wake-up line using `[DONE]`, `[FAILED]`, or `[BLOCKED]`; include:
   - `Indexed-tool contract`: per `shared/indexed-tool-contract.md` (Code
     Indexer first for broad discovery and compact symbol tracing, CodeGraph for
     exact source-backed symbol context, `rg`/`find` only for exact bytes /
     unindexed / generated / outside-index paths; native `auto_reindex`
     freshness via `codeindexer jobs` / `doctor` / `doctor --fix`, no custom git
     hooks).
   - `Finish Report Must Include:` with bullets for code-changing workers:
     - `changed_files`
     - `superpowers_used`
     - `skipped_superpowers`
     - `tests_run`
     - `verification_evidence`
     - `evidence_commands`
   - for anti-regression workers: include `anti_regression_evidence` with
     `classification`, bug class/canonical issue, guardrail evidence, issue
     disposition, and explicit `bug_class_registry_evidence` that shows either
     - `.github/bug-classes.yml` already contains the `bug_class`, or
     - `.github/bug-classes.yml` update is in `changed_files`; Markdown mirror
       updates may accompany it, but are not sufficient by themselves
   - read-only report fields: `findings`, `evidence_commands`, `next_action`
   - required superpowers for worker type (see below).
4. Before launch, ensure selected Kiro agent/config can read local skill roots:
   - `/home/user/.kiro/skills/*`
   - `/home/user/.kiro/skills/*`
   - `/home/user/.kiro/skills/*`
   This belongs in Kiro permissions, not worker prompts.
5. Launch with `scripts/launch_kiro_worker.sh` only.
   - Do not use `kiro-cli chat --no-interactive` headless, `--verbose`, polling, or transcript streaming.
   - For code-changing workers, always pass `WORKER_WORKTREE` set to the path
     returned by `create_worker_worktree.sh` (step 1). Example:

     ```bash
     WORKER_AGENT=kiro-worker \
     WORKER_MODEL=claude-sonnet-4.6 \
     WORKER_ROLE=implementation \
     WORKER_WORKTREE="$WORKTREE_PATH" \
     KIRO_REQUIRED_SKILLS=executing-plans,test-driven-development,verification-before-completion \
     ./scripts/launch_kiro_worker.sh worker-A logs/prompts/worker-A.md
     ```
6. Send wake-up action via the shell tool only after the report is written; do not echo it in final text:

   ```bash
   WORKER_NAME="worker-name"
   REPORT_FILE="logs/REPORT.worker.md"
   ORCH_TARGET="{{ORCH_TARGET}}"
   tmux send-keys -t "$ORCH_TARGET" -l "[DONE] $WORKER_NAME $REPORT_FILE"
   sleep 0.25
   tmux send-keys -t "$ORCH_TARGET" C-m
   ```

   **`{{ORCH_TARGET}}` is substituted by `launch_kiro_worker.sh` at launch time**
   from the orchestrator marker. Workers must NOT hardcode a window name and must
   NOT re-read `.signals/orchestrator-window.json` at runtime — the marker may
   have been refreshed by the time the wake-up runs. The launcher pins the correct
   value at the moment of launch.

   Replace `[DONE]` with `[FAILED]` or `[BLOCKED]` when needed. Use only unique
   `ORCH_TARGET`; avoid pane targets. The orchestrator closes worker windows
   after processing the report — workers must NOT call `tmux kill-window`.
   Workers must NOT merge PRs, delete branches, or close issues — those are
   orchestrator/acceptance decisions. Workers: push → write report → send
   wake-up → stop. Merge/close stay with the orchestrator.

## Agent Selection

| Worker kind | Agent | Model | KIRO_REQUIRED_SKILLS |
|---|---|---|---|
| secretary / read-only | `kiro-worker-flash` | `claude-haiku-4.5` | `swarm-secretary-intake,verification-before-completion` |
| implementation | `kiro-worker` | `claude-sonnet-4.6` | `executing-plans,test-driven-development,verification-before-completion` |
| bug-debug | `kiro-worker` | `claude-sonnet-4.6` | `systematic-debugging,executing-plans,test-driven-development,verification-before-completion` |
| review | `kiro-worker-opus` | `claude-opus-4.8` | `swarm-pr-review-flow,verification-before-completion` |
| review-fix | `kiro-worker-opus` | `claude-opus-4.8` | `swarm-pr-review-flow,receiving-code-review,executing-plans,test-driven-development,verification-before-completion` |

## Required contract checks

- Worker prompts must include:
   - `Required Superpowers`
   - `Forbidden Superpowers`
   - `Indexed-tool contract` per `shared/indexed-tool-contract.md`. If missing,
     do not launch; route back to `swarm-plan` for contract repair.
   - report fields above, selected by worker kind.
   - `anti_regression_contract` when the accepted `SWARM_PLAN` includes one;
     do not launch anti-regression workers with an empty contract.
- Implementation workers require:
  - `superpowers:executing-plans`
  - `superpowers:test-driven-development`
  - `superpowers:verification-before-completion`
- Bugfix/failing-test/security/P0 diagnostics also add:
  - `superpowers:systematic-debugging`
- Review-fix workers require:
  - `superpowers:receiving-code-review`
  - implementation superpowers when code can change.
- P0/security-sensitive/destructive/production/secret-store/SSH/cloud/live-write prompts must include manual-review gate text before destructive steps or acceptance.
- Worker prompts must not ask Kiro workers to spawn the orchestrator subagents for
  swarm execution work. Swarm execution stays in tmux/Kiro workers launched
  by this phase.

## Output

Produce `LAUNCH_RESULT` with:

- `launched_workers`
- `preflight_status`
- `contract` (must be `markdown`)
- `prompt_paths`
- `report_paths`
- `next_action`
- `next_skill`

Omit `next_skill` after successful launches while workers are running.
If a preflight advisory requires revision, emit `next_skill:"swarm-plan"`.
