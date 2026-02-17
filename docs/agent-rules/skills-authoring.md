# Skills Authoring Guide

## Purpose
- Define a single standard for creating, updating, and optimizing Codex skills.
- Keep skills small, deterministic, and easy to execute without interpretation gaps.

## When To Create A Skill
- Create a new skill only for repeated workflows used in 3+ tasks.
- Update an existing skill when the workflow is the same and only details changed.
- Do not create a skill for one-off work or generic coding tasks.

## Required Skill Structure
- `name`: short, unique, action-oriented.
- `description`: clear trigger conditions and explicit non-goals.
- `SKILL.md` sections in this order:
  - Overview
  - Scope
  - Hard Constraints
  - Step-by-step Workflow
  - Validation/Done Criteria
  - Common Failure Modes
  - References (optional)

## Writing Requirements
- Use imperative wording (`Run`, `Check`, `Update`), not vague advice.
- Keep every step testable and observable (command, file, or output).
- Prefer repository-relative paths and exact command examples.
- Separate global rules from local/subtree rules.
- Avoid duplicate instructions already present in `AGENTS.md`.

## Optimization Requirements
- Minimize steps: remove redundant actions and repeated checks.
- Keep context footprint low: reference docs instead of pasting long procedures.
- Front-load critical safety constraints before implementation steps.
- Add fast-fail checks early (missing files, wrong branch, missing env).
- Preserve idempotency where possible (safe to rerun without side effects).

## Quality Gates
- Skill has explicit trigger conditions and explicit non-goals.
- No conflicting instructions with `AGENTS.md` or scoped overrides.
- Commands and file paths are valid in this repository.
- Workflow can be executed end-to-end without external assumptions.
- Skill remains concise; move deep runbooks to `docs/agent-rules/*.md`.

## Change Management
- For edits: keep backward-compatible naming unless scope changed materially.
- If scope changed materially, create a new skill and deprecate the old one.
- Document why the change was made in commit/PR notes.

## Common Anti-Patterns
- Monolithic skill with many unrelated workflows.
- Vague text without measurable success criteria.
- Repeating tool/linter configuration better stored in code config files.
- Embedding secrets, tokens, or environment-specific credentials.
