---
name: swarm-worker-contract
description: Use only in legacy or local the orchestrator swarm workers before finishing implementation, review, review-fix, or operator-skill work; Markdown reports are default, machine JSON is legacy strict_json mode only.
---

# Swarm Worker Contract

This is the default worker finish contract for local/legacy the orchestrator swarm workers.

## Default Finish

Write a compact Markdown report and wake the orchestrator with its path:

```text
[DONE] worker-name logs/REPORT.worker.md
[FAILED] worker-name logs/REPORT.worker.md
[BLOCKED] worker-name logs/REPORT.worker.md
```

For code-changing work, include:

- `status`
- `worker`
- `task`
- `worktree`
- `branch`
- `head_sha`
- `pr`
- `reserved_files`
- `changed_files`
- `superpowers_used`
- `skipped_superpowers`
- `tests_run`
- `verification_evidence`
- `anti_regression_evidence`
- `evidence_commands`
- `summary`
- `blockers`
- `new_bugs`
- `docs_impact`
- `next`

For read-only work, include:

- `status`
- `worker`
- `task`
- `worktree`
- `branch`
- `head_sha`
- `reserved_files`
- `changed_files`
- `summary`
- `findings`
- `risks`
- `superpowers_used`
- `skipped_superpowers`
- `evidence_commands`
- `next`

The orchestrator verifies facts directly. Do not treat the report as proof.

## Discovery And Index Freshness

Follow `shared/indexed-tool-contract.md` when repo/code discovery is needed
(Code Indexer first for broad/semantic discovery and compact caller/reference
tracing, CodeGraph for exact source-backed symbols, `rg`/`find` fallback only;
native `auto_reindex` freshness via `codeindexer jobs` / `doctor` /
`doctor --fix`, no custom git hooks).

## Required Safety Gates

- Work only inside assigned worktree and reserved files.
- Do not switch branches, rebase, merge, push, stash, clean, delete branches,
  create extra worktrees, or edit outside reserved files unless the prompt
  explicitly assigns that operation.
- Do not push. Do not switch branches.
- Do not create or update PRs unless the prompt explicitly assigns that
  operation.
- Do not access production, secrets, SSH, cloud credentials, live CRM writes, or
  real customer data unless explicitly authorized.
- Redact secrets from reports, logs, docs, and prompts.
- Run focused verification requested by the prompt.
- Disposition real bugs: fix in scope or report follow-up.

## Anti-Regression Evidence

For issue bugfix, duplicate, recurrence, umbrella, or bug-class work,
`anti_regression_evidence` is required in the Markdown report:

- `classification`: `new | duplicate | recurrence | umbrella | unknown`
- `bug_class`
- `canonical_issue`
- `related_issues`
- `guardrail_added_or_strengthened`
- `regression_test_or_no_test_rationale`
- `issues_to_close_or_update`
- `closing_comment`
- `bug_class_registry_evidence`

For duplicate, recurrence, umbrella, or any report with a non-empty `bug_class`,
`bug_class_registry_evidence` is mandatory and must prove one of:
- `.github/bug-classes.yml` already contains the class, or
- `.github/bug-classes.yml` is in `changed_files` / report scope with the new
  class added. `docs/engineering/bug-classes.md` may mirror that update, but
  Markdown alone is not source of truth.

If the prompt did not provide enough evidence to classify root cause
similarity, report `classification: unknown` and list the missing evidence in
`blockers`.
Do not claim duplicate/recurrence/umbrella/bug-class work as DONE without valid
`bug_class_registry_evidence`.

## Legacy Strict JSON

Machine JSON artifacts, signal validators, registry state, and wake-up receipts
are legacy strict mode. Use them only when the prompt explicitly sets
`SWARM_CONTRACT=strict_json` or requires automated machine handoff.
