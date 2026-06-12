# PR Review Autofix Guardrails

## Purpose

This process note captures the failure pattern found while auditing PR #2528 and turns it into durable reviewer/orchestrator rules.

The failure was not a production-code bug. The first worker report repeated the old implementation summary and missed the audit blocker: an adjacent focused test still asserted the pre-refactor runtime embedding wrapper contract.

## Owner

Primary owner: `docs/engineering/gh-pr-review.md` / `skills/gh-pr-review.md`.

Secondary owner: `docs/engineering/orchestrator-playbook.md` for prompt-writing discipline.

## Rule 1 — one primary skill per worker prompt

When the orchestrator delegates work to a Codex worker, the prompt must name exactly one primary skill/doc.

Use this routing:

```text
existing PR audit/fix -> docs/engineering/gh-pr-review.md
new issue implementation -> docs/engineering/codex-web-prompt.md
process/skill update -> docs/engineering/orchestrator-playbook.md
```

Do not ask the worker to read a pile of skills as equal authorities. If extra docs are needed, mention them as context only, not as additional primary skills.

## Rule 2 — audit blocker beats old implementation summary

When a PR audit comment identifies a concrete blocker, the next worker must address that blocker first.

The worker must not report the old implementation summary as success unless the blocker file changed, the blocker-specific validation ran, and the PR body/handoff was updated on the new head.

## Rule 3 — adjacent stale tests are safe autofix

If a PR changes a runtime/adapter compatibility contract, the reviewer must inspect adjacent tests for stale assertions against the old contract.

Examples:

- removed framework inheritance, such as `langchain_core.embeddings.Embeddings`;
- replaced direct `_client` ownership with `_provider` delegation;
- moved endpoint/client behavior behind a canonical provider;
- renamed/moved shim classes while preserving import compatibility.

If tests assert the old contract, classify the failure as `stale_test` related to the changed architecture and autofix the test in the same PR.

Do not delete, skip, xfail, or weaken the test. Retarget it to the new contract while preserving behavior coverage.

## Required reviewer checklist for this class of change

For runtime/adapter compatibility changes, the reviewer must:

1. Inspect the changed production files and identify contract changes.
2. Search adjacent tests for old contract symbols, imports, private attrs, and class inheritance assumptions.
3. Retarget stale tests to the new contract.
4. Add those tests to focused validation.
5. Add the touched test file to PR body `Changed files / scope`.
6. Update Agent Handoff with the new validated commit and green required GitHub checks.

A PR is not clean if the adjacent stale-test blocker is still only documented in comments or if validation does not include the retargeted test file.

## Example from PR #2528

Old stale assertions:

```python
from langchain_core.embeddings import Embeddings
assert isinstance(emb, Embeddings)
assert emb._client is not None
client = await emb._client._get_client()
```

Correct retargeted assertions:

```python
from src.adapters.embeddings.bge_m3 import BgeM3EmbeddingProvider
assert isinstance(emb._provider, BgeM3EmbeddingProvider)
assert emb._provider is provider
assert emb._provider._client is client
client = await emb._provider._client._get_client()
```

Focused validation must include the adjacent test file:

```bash
uv run --no-sync pytest -o addopts='' tests/unit/integrations/test_embeddings.py tests/unit/retrieval/ tests/unit/services/test_bge_m3_client.py -q
```
