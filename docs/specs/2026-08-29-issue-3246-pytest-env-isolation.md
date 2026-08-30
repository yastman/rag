# Issue #3246 Pytest Environment Isolation Specification

## Outcome

Pytest may load an ignored `.env` from the current checkout only. It must never discover and load an ancestor checkout's `.env` when the test process runs from an internal Git worktree.

## Evidence

Before this change, `tests/conftest.py` called `load_dotenv()` without a path. `python-dotenv` searches upward, so `.worktrees/issue-*` could inherit the primary checkout's operator credentials. In the #3201 worktree, the worktree had no `.env`, the parent checkout did, and the E2E missing-key test failed because a provider key became visible. With `PYTHON_DOTENV_DISABLED=1`, that exact test passed.

No credential value is needed to reproduce or verify this defect.

## Contract

- Resolve the dotenv path from `tests/conftest.py` to the current Git worktree root explicitly.
- Preserve the existing `PYTHON_DOTENV_DISABLED` opt-out.
- Preserve ordinary primary-checkout behavior: if `<current-checkout>/.env` exists, it may be loaded with dotenv's default non-overriding semantics.
- If the current checkout has no `.env`, load nothing; never search parent directories.
- Add a runtime contract that proves the shared pytest bootstrap passes exactly the current-checkout path and preserves the opt-out.
- Do not print, inspect, copy, or commit `.env` contents.

## Owned Files

- `tests/conftest.py`
- `tests/contract/test_pytest_dotenv_scope_contract.py` (new)

## Non-Goals

- Production settings or source adapters.
- E2E provider policy.
- Clearing inherited process environment variables.
- Dependency changes or a generic dotenv abstraction.

## Acceptance

1. The runtime contract rejects the old unbounded call and any extra positional or keyword arguments, and passes on the explicit worktree-local path.
2. `tests/unit/e2e_adapters/test_config.py` passes without setting `PYTHON_DOTENV_DISABLED` externally.
3. Existing environment variables retain precedence.
4. No tracked or ignored environment file is modified.

## Rollback

Revert this issue's commits. There is no runtime or data migration.
