***REMOVED*** Swarm Superpowers Worker Policy External Changes

This manifest records changes made outside the `rag-fresh` git repository while
executing `2026-05-20-swarm-superpowers-worker-policy.md`.

***REMOVED******REMOVED*** Format

For each external change, append:

```markdown
***REMOVED******REMOVED******REMOVED*** YYYY-MM-DD Task N: short title

- Files changed:
- Backup paths:
- Verification commands:
- Result:
- Notes:
```

No external changes have been applied yet.

***REMOVED******REMOVED******REMOVED*** 2026-05-20 Task 2: swarm plan allocation and orchestrator boundary

- Files changed:
  - `/home/user/.codex/skills/swarm-plan/SKILL.md`
  - `/home/user/.codex/skills/swarm-orchestrator/SKILL.md`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_plan_contract.py`
- Backup paths: none
- Verification commands:
  - `pytest tests/test_swarm_plan_contract.py -q` from `/home/user/.codex/skills/tmux-swarm-orchestration` failed because `pytest` is not installed on PATH.
  - `uv run pytest tests/test_swarm_plan_contract.py -q` from `/home/user/.codex/skills/tmux-swarm-orchestration` failed because the external directory has no pytest environment.
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_swarm_plan_contract.py -q`
- Result: `2 passed`
- Notes: external swarm skill directories are not git repositories on this machine, so these file changes are recorded here rather than committed from the repo.

***REMOVED******REMOVED******REMOVED*** 2026-05-20 Task 3: launcher Superpowers skill resolution

- Files changed:
  - `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/launch_opencode_worker.sh`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_launch_opencode_worker.py`
- Backup paths: none
- Verification commands:
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_launch_opencode_worker.py -q`
- Result: `4 passed`
- Notes: launcher now accepts `superpowers:<slug>` / `superpowers/<slug>`, searches OpenCode plugin and Codex Superpowers paths, rejects worker-forbidden Superpowers, and bundles namespaced skills under filesystem-safe names.

***REMOVED******REMOVED******REMOVED*** 2026-05-20 Task 4: prompt validator Superpowers policy

- Files changed:
  - `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_validate_worker_prompt.py`
- Backup paths: none
- Verification commands:
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_validate_worker_prompt.py -q`
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_launch_opencode_worker.py tests/test_validate_worker_prompt.py -q`
- Result: `4 passed`; `8 passed`
- Notes: validator now requires Superpowers policy and finish-report fields for code-changing workers, rejects forbidden worker Superpowers in `Required Superpowers`, and allows docs-only TDD skips with a reason.

***REMOVED******REMOVED******REMOVED*** 2026-05-20 Tasks 5-10: launch, worker, acceptance, OpenCode, signal, dry-run contracts

- Files changed:
  - `/home/user/.codex/skills/swarm-launch/SKILL.md`
  - `/home/user/.codex/skills/swarm-worker-contract/SKILL.md`
  - `/home/user/.codex/skills/swarm-acceptance/SKILL.md`
  - `/home/user/.config/opencode/skills/swarm-worker-contract/SKILL.md`
  - `/home/user/.config/opencode/skills/swarm-pr-finish/SKILL.md`
  - `/home/user/.config/opencode/agents/pr-worker.md`
  - `/home/user/.config/opencode/agents/pr-review-fix.md`
  - `/home/user/.config/opencode/agents/pr-review.md`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_launch_contract.py`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_worker_contract.py`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_acceptance_contract.py`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_opencode_agent_contract.py`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_validate_worker_signal.py`
  - `/home/user/.codex/skills/tmux-swarm-orchestration/tests/test_swarm_superpowers_dry_run.py`
- Backup paths: none
- Verification commands:
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_swarm_launch_contract.py -q`
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_worker_contract.py -q`
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_swarm_acceptance_contract.py -q`
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_opencode_agent_contract.py -q`
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_validate_worker_signal.py -q`
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_swarm_superpowers_dry_run.py -q`
  - `/home/user/projects/rag-fresh/.worktrees/plan-swarm-superpowers-worker-policy/.venv/bin/python -m pytest tests/test_launch_opencode_worker.py tests/test_validate_worker_prompt.py tests/test_validate_worker_signal.py tests/test_swarm_plan_contract.py tests/test_swarm_launch_contract.py tests/test_worker_contract.py tests/test_swarm_acceptance_contract.py tests/test_opencode_agent_contract.py tests/test_swarm_superpowers_dry_run.py -q`
- Result: individual task checks passed; full external swarm subset `18 passed`.
- Notes: `swarm-launch` now documents preflight gates; worker contracts and OpenCode agents now constrain branch/worktree/push behavior; acceptance now verifies `changed_files`/`reserved_files`/Superpowers evidence and disposition; signal validator accepts namespaced Superpowers arrays; dry-run test does not launch tmux/OpenCode.
