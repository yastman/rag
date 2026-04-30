# W-1269-quick-cleanup: quick cleanup bundle

## ROLE
You are an OpenCode implementation worker. Work only in the assigned worktree. Implement, test, commit, push, open a PR, and write DONE JSON.

## TASK
Fix GitHub issue #1269: quick cleanup bundle.

Issue: https://github.com/yastman/rag/issues/1269

## IMPLEMENTATION BRIEF
Goal: Apply the safe repository-file cleanup items from #1269 without touching unrelated worktrees or active branches.

Acceptance criteria:
- Remove duplicate `test-unit-core` Makefile target if it is still identical to `test-unit`.
- Make Makefile help banner use `$(PROJECT_VERSION)` instead of stale hardcoded `v2.0.1`.
- Remove the broken `.gitignore` `!docs/plans/` directory re-include line, preserving explicit file re-includes.
- Add explicit `typing-extensions` dependency in `pyproject.toml` and update `uv.lock` consistently.
- Move or rename `tests/benchmark/test_docling_metadata_deep.py` so pytest no longer treats it as a test file, preserving the analysis script content.
- Do not remove worktrees from inside the worker. If the stale worktree item still applies, report it as an `out_of_scope_issue`/orchestrator cleanup finding in DONE JSON.

Reserved files:
- Makefile
- .gitignore
- pyproject.toml
- uv.lock
- tests/benchmark/test_docling_metadata_deep.py
- tests/benchmark/_docling_metadata_deep.py

Suggested implementation:
- Prefer renaming `tests/benchmark/test_docling_metadata_deep.py` to `tests/benchmark/_docling_metadata_deep.py`.
- Use `uv lock` or repo-standard dependency locking after editing `pyproject.toml`.
- Keep edits minimal.

Verification ladder:
- `git diff --check`
- `uv run pytest tests/unit/test_dependency_workflow.py -q` if dependency/lock tests exist and are relevant
- `uv run pytest tests/benchmark -q` or a collection-only check proving the renamed analysis script is not collected
- `make check`

Non-goals:
- Do not remove local worktrees or branches.
- Do not clean unrelated stale worker directories.
- Do not rewrite Makefile/test structure beyond listed cleanup items.

Done definition:
- Commit and push branch `fix/1269-quick-cleanup`.
- Open PR against `dev` with `Fixes #1269`.
- DONE JSON includes `findings[]`; use `out_of_scope_issue` if stale worktree cleanup remains for orchestrator.

## WORKTREE ISOLATION
WORKTREE=/home/user/projects/rag-fresh-wt-1269-quick-cleanup
BRANCH=fix/1269-quick-cleanup
RESERVED_FILES=Makefile, .gitignore, pyproject.toml, uv.lock, tests/benchmark/test_docling_metadata_deep.py, tests/benchmark/_docling_metadata_deep.py

## REQUIRED SKILLS WORKFLOW
Use `superpowers:test-driven-development`, then `swarm-self-review`, then `superpowers:verification-before-completion`, then `swarm-pr-finish`.
Record markers in `logs/worker-1269-quick-cleanup.log`.

## SIGNALING
ORCH_PANE=%26
SIGNAL_FILE=/home/user/projects/rag-fresh-wt-1269-quick-cleanup/.signals/worker-1269-quick-cleanup.json

Write DONE JSON atomically via `.tmp` then `mv`. After writing it, run:

```bash
tmux send-keys -t "%26" "[DONE] W-1269-quick-cleanup /home/user/projects/rag-fresh-wt-1269-quick-cleanup/.signals/worker-1269-quick-cleanup.json"
sleep 1
tmux send-keys -t "%26" Enter
```
