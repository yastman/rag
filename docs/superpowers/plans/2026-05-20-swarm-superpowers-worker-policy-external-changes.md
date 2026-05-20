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
