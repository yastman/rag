# OpenCode Swarm Workers Design

Date: 2026-05-11

## Goal

Move the tmux swarm execution layer from Codex `321` workers to OpenCode
workers while keeping Codex as the orchestrator.

Codex remains responsible for control-plane decisions: selecting issues or PRs,
decomposing work, reserving files, creating worktrees, writing worker prompts,
launching workers, validating signal artifacts, reviewing bounded diffs,
running acceptance verification, and deciding merge, review-fix, cleanup, or
follow-up issue disposition.

OpenCode becomes the worker runner for implementation, PR review, review-fix,
CI/status polling, local verification, signal/schema validation, docs/mechanical
tasks, and post-merge cleanup.

## Non-Goals

- Do not replace Codex as the orchestrator.
- Do not keep Codex `321` as an active default worker path.
- Do not introduce a generic multi-runner abstraction unless a concrete fallback
  need appears after the OpenCode path works.
- Do not move PR branch edits, implementation, or review-fix work back into the
  orchestrator.
- Do not depend on prompt prose alone to prove that workers can load required
  skills.

## Current Context

The existing `tmux-swarm-orchestration` skill is deeply tied to Codex `321`:

- `SKILL.md` names Codex `321` workers and Codex model routing.
- `infrastructure.md` records registry entries with `runner:"codex-321"`.
- `scripts/launch_codex321_worker.sh` starts `321` in a dedicated tmux window.
- `worker-contract.md` and references require strict DONE JSON and wake-up
  artifacts.
- Tests assert launcher and documentation contracts, including legacy
  OpenCode-forbidden text that must be replaced during migration.

The repository already has OpenCode worker infrastructure:

- project agents:
  - `.opencode/agents/pr-worker.md`
  - `.opencode/agents/pr-review-fix.md`
  - `.opencode/agents/complex-escalation.md`
- global agent:
  - `~/.config/opencode/agents/pr-review.md`
- OpenCode skills:
  - `.opencode/skills/gh-pr-review/SKILL.md`
  - `~/.config/opencode/skills/project-docs-maintenance/SKILL.md`
  - `~/.config/opencode/skills/swarm-bug-reporting/SKILL.md`
  - `~/.config/opencode/skills/swarm-pr-finish/SKILL.md`
  - `~/.config/opencode/skills/swarm-review-fix/SKILL.md`

Installed OpenCode version is `1.3.17`. The CLI supports `opencode run` with
`--agent`, `--model`, `--variant`, `--dir`, `--file`, and `--format`.

## Proposed Architecture

### Orchestrator

Codex keeps the same control-plane role:

1. Gather GitHub and repository context.
2. Classify the work.
3. Choose worker type, OpenCode agent, model, and variant.
4. Reserve files and create a dedicated git worktree.
5. Write a worker prompt file.
6. Validate that OpenCode agents and required skills are available.
7. Launch the worker in a dedicated tmux window.
8. Validate DONE, FAILED, or BLOCKED signal artifacts.
9. Review diffs and PR metadata.
10. Run or delegate final verification.
11. Decide merge, review-fix, cleanup, or follow-up issue creation.

The orchestrator may edit only control-plane artifacts such as prompts, registry
entries, signal status, and design/skill infrastructure. It must not patch PR
branches inline for issue delivery or review-fix work.

### Worker Runner

Introduce an OpenCode launcher, tentatively:

```text
scripts/launch_opencode_worker.sh
```

The launcher keeps the current tmux isolation model:

- one worker per dedicated tmux window;
- one git worktree per active worker;
- prompt stored in a worker-local file;
- terminal receives only a short prompt-file instruction;
- launch metadata persisted to `.signals/launch-*.json`;
- raw TUI/run output saved to a bounded log path for failure investigation;
- DONE/FAILED/BLOCKED still use worker-local JSON plus tmux wake-up.

The launcher runs OpenCode in the worker worktree, for example:

```bash
opencode run \
  --agent "$OPENCODE_AGENT" \
  --model "$OPENCODE_MODEL" \
  --variant "$OPENCODE_VARIANT" \
  --dir "$WT_PATH" \
  "Read and execute the worker prompt file at: $PROMPT_FILE"
```

The exact command may add `--format json` or local-only permission/config
controls after smoke testing confirms the best behavior for visible tmux runs.

### Registry Metadata

Update active-worker registry and launch metadata from Codex-specific fields to
OpenCode fields:

```json
{
  "worker": "W-name",
  "runner": "opencode",
  "worktree": "/abs/worktree",
  "branch": "branch-name",
  "base": "dev",
  "signal_file": "/abs/worktree/.signals/worker-name.json",
  "prompt_sha256": "sha256",
  "agent": "pr-worker",
  "model": "opencode-go/kimi-k2.6",
  "variant": "",
  "reserved_files": ["path"],
  "started_at": "ISO-8601",
  "status": "active"
}
```

`reasoning_effort` should be retired for OpenCode workers and replaced with
`variant`, because OpenCode exposes model-specific reasoning effort through
`--variant`.

## Worker Types And OpenCode Agents

Default worker routing:

| Worker type | OpenCode agent | Required skills |
| --- | --- | --- |
| implementation / PR worker | `pr-worker` | `project-docs-maintenance`, `swarm-bug-reporting`, `swarm-pr-finish` |
| PR review | `pr-review` | `gh-pr-review`, `project-docs-maintenance`, `swarm-review-fix`, `swarm-bug-reporting`, `swarm-pr-finish` |
| review-fix | `pr-review-fix` | `gh-pr-review`, `swarm-review-fix`, `project-docs-maintenance`, `swarm-bug-reporting`, `swarm-pr-finish` |
| docs worker | `pr-worker` or a future `docs-worker` | `project-docs-maintenance`, `swarm-bug-reporting`, `swarm-pr-finish` |
| CI/status polling | future narrow read-only agent or `pr-review` | none by default; strict DONE contract still applies |
| local verification | future narrow read-only agent or `pr-review` | `swarm-pr-finish` only when writing full DONE JSON |
| signal/schema validation | future artifact-check agent | none by default; validates signal schema only |
| post-merge cleanup | future cleanup agent | `swarm-pr-finish` only when writing full DONE JSON |

The initial migration can reuse existing agents and add narrow agents later when
permissions need to be tighter.

## Required Skill Availability Gate

Worker prompts must include an explicit `REQUIRED OPENCODE SKILLS` block, but
that is not sufficient. The orchestrator or launcher must also validate that the
skills are available before worker launch.

Validation checks:

1. The selected OpenCode agent exists in project or global OpenCode agent paths.
2. Each required skill exists in at least one OpenCode discovery path:
   - `.opencode/skills/<name>/SKILL.md`
   - `~/.config/opencode/skills/<name>/SKILL.md`
   - `.agents/skills/<name>/SKILL.md`
   - `~/.agents/skills/<name>/SKILL.md`
   - `.claude/skills/<name>/SKILL.md`
   - `~/.claude/skills/<name>/SKILL.md`
3. Skill names are OpenCode-compatible lowercase hyphen names.
4. The selected agent grants the `skill` permission broadly enough to load the
   required skills.
5. Launch metadata records `required_skills` and `skills_available:true`.

Prompt contract:

```text
REQUIRED OPENCODE SKILLS
- Load these skills in order before doing substantive work:
  1. project-docs-maintenance
  2. swarm-bug-reporting
  3. swarm-pr-finish
- If any skill is unavailable, write status:"blocked" DONE JSON with the missing
  skill name and wake the orchestrator.
- Record the loaded skills in DONE JSON as:
  "skills_loaded": ["project-docs-maintenance", "swarm-bug-reporting", "swarm-pr-finish"]
```

The orchestrator validates `skills_loaded` against `required_skills`. Missing or
renamed skills are contract failures, not warnings.

## Documentation Skill Contract

`project-docs-maintenance` is the OpenCode documentation skill.

Use it as follows:

- implementation workers use it when code, config, tests, runtime behavior,
  public commands, service boundaries, API routes, env vars, dependencies, or
  user-visible workflow can affect docs;
- docs workers use it as the primary workflow;
- review-fix workers use it when blocker fixes affect documented contracts;
- PR review workers use it as a review gate when the PR touches documentation or
  a documented contract.

DONE JSON must record one of:

- docs updated in reserved files;
- docs impact checked and not impacted;
- docs impacted but canonical docs are outside `RESERVED_FILES`, with a
  `new_bugs` or disposition entry for orchestrator decision.

## Prompt Contract Changes

Replace Codex-specific prompt language with OpenCode-native terms:

- `Codex 321 worker` -> `OpenCode worker`
- `CODEX_MODEL` -> `OPENCODE_MODEL`
- `CODEX_REASONING_EFFORT` -> `OPENCODE_VARIANT`
- `Codex-native skills` -> `OpenCode skills`
- `REQUIRED SKILLS WORKFLOW` -> `REQUIRED OPENCODE SKILLS` plus worker-type
  workflow steps

Prompts should keep the existing strong contracts:

- work only in the assigned worktree;
- edit only reserved files;
- obey docs lookup policy;
- do not browse when policy is forbidden;
- write strict DONE JSON through a structured serializer;
- self-check JSON before wake-up;
- wake the orchestrator with submitted tmux input, not just visible text;
- stop after finish-only conditions are reached.

## DONE JSON Changes

Keep the strict existing shape and add OpenCode-specific fields:

```json
{
  "runner": "opencode",
  "agent": "pr-worker",
  "model": "opencode-go/kimi-k2.6",
  "variant": "",
  "required_skills": ["project-docs-maintenance", "swarm-bug-reporting", "swarm-pr-finish"],
  "skills_loaded": ["project-docs-maintenance", "swarm-bug-reporting", "swarm-pr-finish"]
}
```

The following remain required:

- `status`
- `worker`
- `branch`
- `head_ref`
- `head_sha`
- `base`
- `changed_files`
- `pr_files`
- `reserved_files`
- `prompt_sha256`
- `review_decision`
- `findings`
- `blockers_found`
- `blockers_resolved`
- `new_bugs`
- `bug_disposition_recommendations`
- `sdk_native_check`
- `sdk_docs_evidence`
- `commands`
- `summary`
- `next_action`
- `ts`

The orchestrator rejects legacy aliases such as `files_changed`, `checks`,
`verification`, `blockers`, `status:"DONE"`, and string-only `commands`.

## Local-Only And Docs Lookup Policy

OpenCode has its own permission and MCP model, so `SWARM_LOCAL_ONLY=1` cannot be
ported as a blind environment variable replacement.

The migration should preserve the policy in three layers:

1. Prompt: every worker gets an explicit docs lookup policy.
2. Agent permissions: read-only and local-only agents deny or restrict
   `webfetch`, `websearch`, and external directories where appropriate.
3. Launch metadata: record whether local-only enforcement was requested and what
   agent/permission assumptions were used.

OpenCode config already supports permissions and per-agent permissions. The
implementation plan should decide whether to enforce local-only through a
temporary generated config, dedicated local-only agents, or launcher validation
against existing agent files.

## Tests And Validation

Migration should update the skill's tests rather than deleting contract coverage.

Required tests:

1. Launcher docs and script use `opencode`, not `codex-321`, for active worker
   examples.
2. Registry examples contain `runner:"opencode"`, `agent`, `model`, and
   `variant`.
3. Required skill availability is documented and tested.
4. Worker prompt references require `REQUIRED OPENCODE SKILLS`.
5. DONE JSON examples include `required_skills` and `skills_loaded`.
6. Old anti-OpenCode test is replaced with an anti-legacy-Codex-worker test.
7. The launcher refuses missing `ORCH_PANE`, missing prompt file, missing
   worktree, missing agent, or missing required skill.
8. Local-only/docs lookup policy is still represented in prompt and launch
   metadata.

Manual smoke test:

1. Create a temporary worktree.
2. Launch a minimal OpenCode worker in tmux.
3. Require it to load the selected skills.
4. Require compact DONE JSON with `skills_loaded`.
5. Require tmux wake-up to the orchestrator pane.
6. Validate registry, launch metadata, prompt SHA, and signal JSON.
7. Close the worker tmux window.

## Migration Plan Outline

1. Update `tmux-swarm-orchestration` documentation to make OpenCode workers the
   active path and Codex `321` a removed legacy runner.
2. Add `scripts/launch_opencode_worker.sh` based on the existing tmux launcher,
   preserving orchestrator pane validation, prompt placeholder replacement,
   launch metadata, raw log, and exit artifact behavior.
3. Add skill/agent discovery validation to the launcher or a small helper script.
4. Update worker prompt references for OpenCode agents, skills, model/variant,
   and DONE JSON fields.
5. Update tests to lock the new contract.
6. Run unit tests for the skill docs/launcher contract.
7. Run one real tmux OpenCode smoke worker.
8. Record swarm feedback with the smoke result and any worker drift.

## Acceptance Criteria

- The orchestration skill no longer instructs active workers to use Codex `321`.
- OpenCode is the active runner in infrastructure docs, launch command examples,
  registry examples, worker prompt guidance, and tests.
- The orchestrator remains Codex and keeps PR delivery role boundaries.
- Worker prompts name required OpenCode skills in order.
- The launcher fails before launch if required OpenCode skills or agents are
  missing.
- DONE JSON records `runner`, `agent`, `model`, `variant`, `required_skills`,
  and `skills_loaded`.
- Documentation impact uses `project-docs-maintenance`.
- A real OpenCode smoke worker can load skills, write valid DONE JSON, and wake
  the orchestrator.

## Open Questions For Implementation

- Should local-only enforcement use dedicated OpenCode agents or generated
  per-launch config?
- Should PR review get a project-local `pr-review` agent instead of relying on
  the global one?
- Should narrow agents be added immediately for CI/status, artifact-check,
  local-verification, and cleanup, or should the first migration reuse existing
  agents and tighten later?
- Which OpenCode models should replace the current `gpt-5.3-codex` and Spark
  routing table for each worker type?
