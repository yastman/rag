# SDK Gate Split Design

## Status

Approved for spec on 2026-05-13.

## Goal

Split SDK-native decision making from swarm worker orchestration without
making `tmux-swarm-orchestration` a large research skill.

`tmux-swarm-orchestration` remains the single launch entrypoint and owns task
classification, baseline enforcement, worker prompt injection, docs lookup
restrictions, and acceptance checks.

`sdk-research` becomes the source of truth for SDK/custom decisions and returns
a worker-ready SDK baseline block.

## Design

The orchestrator classifies each task before worker launch:

- `not_applicable`: local docs/config/test drift or edits that do not affect
  SDK, API, framework, or runtime behavior.
- `sdk_sensitive`: work that may affect SDK clients, API behavior, framework
  lifecycle, auth, retries, pagination, vector search, runtime health,
  Docker/Compose semantics, or equivalent native-vs-custom decisions.
- `inconclusive`: the orchestrator cannot determine a safe baseline from local
  registry, current code, or current docs.

For `not_applicable`, no SDK gate is required. The worker prompt should still
state why SDK-native checking is not applicable.

For `sdk_sensitive`, the orchestrator must run `sdk-research` before launching
implementation workers. The resulting baseline is pasted into the worker
prompt. Workers do not perform open-ended SDK or external docs research.

For `inconclusive`, implementation workers must not launch. The next step is a
research, docs-maintenance, or registry-update task that produces enough
baseline for a later implementation launch.

## Responsibilities

`sdk-research` owns knowledge acquisition:

- find the repo-native SDK registry through nearest `AGENTS.md` or
  `AGENTS.override.md`, then canonical docs such as
  `docs/engineering/sdk-registry.md`;
- inspect existing repo-native usage patterns with focused `rg` searches;
- use Context7 only when local patterns are insufficient or version-sensitive
  API behavior matters;
- return a structured `SDK/custom decision` block ready for worker prompts;
- recommend registry or docs updates when local knowledge is absent, stale, or
  contradicted by current usage.

`tmux-swarm-orchestration` owns enforcement:

- classify SDK sensitivity during intake or decomposition;
- require `sdk-research` output before SDK-sensitive implementation launch;
- inject the baseline into worker prompts;
- set worker docs lookup policy, normally `forbidden`;
- require workers to block when the baseline is missing or insufficient;
- reject acceptance when DONE JSON does not match the SDK gate.

## Baseline Format

`sdk-research` should return this worker-ready block:

```text
SDK/custom decision:
classification: sdk_sensitive | not_applicable | inconclusive
registry_source: docs/engineering/sdk-registry.md or not_found
local_pattern: src/foo.py::bar or not_found
sdk_docs_evidence:
- local: src/foo.py::bar
- registry: docs/engineering/sdk-registry.md
- docs: Context7 /org/library, if used
version_assumption:
- known_version: package==x.y.z or image tag, if known
- unknown_version: package/runtime version not found, if unknown
required_shape:
- use the repo-native or SDK-native API shape
forbidden_custom:
- custom clients, transports, parsers, lifecycle handling, auth, retries,
  pagination, vector/search wrappers, or runtime behavior that duplicates the
  SDK/framework
allowed_custom:
- thin glue explicitly listed here
worker_docs_lookup_policy: forbidden unless a scoped Context7 refresh is
  explicitly required
done_json_expectation:
- sdk_native_check=native_used | custom_justified | blocker | not_applicable
- custom_justification=<empty unless custom_justified>
- sdk_docs_evidence=<array>
```

`classification: inconclusive` means no implementation launch. The orchestrator
must create a follow-up research/docs/registry task or perform the missing
research itself before launching implementation.

## Worker Contract

Implementation workers are not allowed to invent SDK clients, parsers,
transports, lifecycle handling, auth, retries, pagination, or framework
behavior when an SDK baseline is missing or insufficient. They must block
instead.

The blocked signal should be machine-checkable:

```json
{
  "status": "blocked",
  "block_reason": "missing_or_insufficient_sdk_baseline",
  "needed_from_orchestrator": "sdk/custom decision with required_shape and forbidden_custom"
}
```

Custom code is allowed only when explicitly listed as allowed glue or when
justified through `custom_justification` and accepted by the orchestration
gate.

## Acceptance Rules

For SDK-sensitive work, acceptance fails when:

- the prompt lacks an orchestrator-supplied `SDK/custom decision`;
- the worker used broad docs lookup, web search, Exa, or Context7 while the
  docs lookup policy was `forbidden`;
- DONE JSON omits `sdk_native_check`;
- `sdk_native_check` conflicts with the baseline;
- custom-looking SDK/framework/runtime behavior appears without concrete
  `custom_justification`;
- `sdk_docs_evidence` is missing when Context7 or official docs were used.

For `not_applicable`, DONE JSON should set `sdk_native_check` to
`not_applicable` and keep `custom_justification` empty.

For `inconclusive`, an implementation DONE JSON is invalid because
implementation should not have launched.

## Example: Issue 1510

Apply the SDK gate to Qdrant auth, LiveKit/voice health behavior, and
Docker/Compose semantics because these are SDK/runtime-sensitive.

Treat stale docs, env examples, README links, and local documentation drift as
local docs work unless they also change SDK/API/runtime behavior.

## Files Expected To Change During Implementation

- `/home/USER/.codex/skills/sdk-research/SKILL.md`
- `/home/USER/.codex/skills/tmux-swarm-orchestration/SKILL.md`
- `/home/USER/.codex/skills/tmux-swarm-orchestration/references/sdk-native.md`
- `/home/USER/.codex/skills/tmux-swarm-orchestration/references/worker-prompt.md`
- `/home/USER/.codex/skills/tmux-swarm-orchestration/references/prompt-snippets.md`
- `/home/USER/.codex/skills/tmux-swarm-orchestration/references/signal-schema.md`
- `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_prompt.py`
- `/home/USER/.codex/skills/tmux-swarm-orchestration/scripts/validate_worker_signal.py`
- focused tests under
  `/home/USER/.codex/skills/tmux-swarm-orchestration/tests/`

## Non-Goals

- Do not move tmux launch, registry, signal, or DONE JSON ownership into
  `sdk-research`.
- Do not let implementation workers perform open-ended SDK discovery.
- Do not create a new project-knowledge skill in this iteration.
- Do not require Context7 for local-only docs/config/test drift.
