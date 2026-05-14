# Worker-First Swarm Orchestration Design

Date: 2026-05-14
Status: Draft approved for planning
Scope: `$tmux-swarm-orchestration` skill package and its OpenCode worker routes

## Problem

`tmux-swarm-orchestration` currently describes Codex as a thin orchestrator, but
the package still makes the orchestrator spend expensive GPT-5.5 context on
work that can be delegated:

- queue and issue discovery;
- issue/PR body reading;
- decomposition and file reservation analysis;
- SDK/runtime baseline research;
- worker prompt drafting;
- artifact and signal checks;
- semantic diff review;
- verification selection;
- new bug disposition research.

The current model prevents Codex from editing directly, but it still lets the
orchestrator become the primary analyst. The target behavior is stricter:
Codex should be a decision layer that launches workers, validates contracts,
routes the next step, and asks the user only for product, safety, access, or
production decisions.

## Goals

- Move broad discovery and analysis from the orchestrator to workers.
- Add two secretary worker routes:
  - `secretary-flash`: `opencode-go/deepseek-v4-flash`
  - `secretary-pro`: `opencode-go/deepseek-v4-pro`
- Keep `pr-worker` on Kimi K2.6 as the primary implementation route.
- Let secretary workers return compact artifacts and draft prompts for the next
  worker.
- Make the orchestrator validate artifacts and choose routes without reading
  raw transcripts, large diffs, full issue bodies, SDK docs, or broad logs.
- Add guardrails so launcher metadata cannot claim one model while OpenCode
  actually uses another agent-frontmatter model.

## Non-Goals

- Do not let secretary workers launch other workers directly.
- Do not remove dedicated implementation, review, review-fix, runtime, or docs
  worker roles.
- Do not allow workers to bypass production, secret, SSH, cloud, or live CRM
  safety rules.
- Do not make headless OpenCode delivery the default; visible tmux sessions
  remain the runner contract.
- Do not require secretary workers for truly tiny local/operator tasks.

## Model Research Baseline

DeepSeek official docs describe DeepSeek V4 Preview as released on
2026-04-24 with both V4-Pro and V4-Flash. Both support 1M context, JSON output,
tool calls, thinking and non-thinking modes, and OpenAI/Anthropic API formats.

Official model facts used for routing:

- V4-Flash: 284B total parameters, 13B active per token; positioned as the
  fast, economical model. Official list pricing is `$0.14/M` cache-miss input,
  `$0.0028/M` cache-hit input, and `$0.28/M` output.
- V4-Pro: 1.6T total parameters, 49B active per token; positioned for stronger
  reasoning, coding, and agentic tasks. Official pricing during the current
  promo is `$0.435/M` cache-miss input, `$0.003625/M` cache-hit input, and
  `$0.87/M` output, with list prices `$1.74/M`, `$0.0145/M`, and `$3.48/M`.

Sources:

- <https://api-docs.deepseek.com/news/news260424>
- <https://api-docs.deepseek.com/quick_start/pricing>

## Architecture

The swarm becomes a worker-first control plane:

```text
User request
  -> orchestrator route decision
  -> secretary-flash for cheap discovery by default
  -> secretary-pro when scope/risk/confidence requires deeper analysis
  -> pr-worker on Kimi K2.6 for implementation
  -> pr-review for semantic review
  -> pr-review-fix for named blockers
  -> final orchestrator decision from valid artifacts
```

The orchestrator remains responsible for:

- launching workers in dedicated worktrees;
- enforcing worker capacity and reservation conflicts;
- validating signal JSON, launch metadata, model route, and artifact paths;
- deciding whether to launch the next worker, escalate, ask the user, or finish;
- final reporting.

The orchestrator no longer owns by default:

- raw issue/PR research;
- full code discovery;
- SDK/docs research;
- decomposition;
- semantic diff review;
- broad log reading;
- prompt drafting beyond minimal corrections;
- verification command discovery.

## Worker Roles

### Secretary Flash

Route:

```text
agent=secretary-flash
model=opencode-go/deepseek-v4-flash
contract=quick by default
```

Use for:

- queue selection;
- issue/PR summary;
- backlog clustering;
- CI/status snapshots;
- signal/schema/artifact checks;
- simple `gh`, `rg`, `git status`, and bounded local reads;
- draft next worker prompt for low-risk tasks.

Default constraints:

- no source edits unless files are explicitly reserved;
- no issue label/comment changes;
- no PR creation;
- no broad tests;
- no web/docs/MCP unless the prompt explicitly allows it;
- writes only logs, signals, and optional prompt drafts.

### Secretary Pro

Route:

```text
agent=secretary-pro
model=opencode-go/deepseek-v4-pro
contract=quick or full depending on artifact type
```

Use for:

- unclear scope;
- complex decomposition;
- many files or cross-surface impact;
- SDK/API/runtime/Compose/Langfuse/k8s risk;
- conflicting worker reports;
- review of `secretary-flash` artifacts;
- SDK/runtime baseline production;
- refined implementation/review prompt drafts.

Default constraints:

- no product/source edits unless launched as a docs/research phase with
  reserved docs files;
- no delivery PRs;
- no merge/cleanup decisions;
- may use Context7/official docs only when the prompt scopes the library and
  question.

### PR Worker

Route remains:

```text
agent=pr-worker
model=opencode-go/kimi-k2.6
```

Use for implementation, tests, docs, PR creation/update, and focused
verification selected by accepted secretary artifacts.

### PR Review

Route remains read-only. It performs semantic review and replaces the current
rule that the orchestrator must deeply inspect the diff.

### PR Review-Fix

Fixes only named blockers from accepted review artifacts or failed checks.

## Routing Policy

Use `secretary-flash` first when one of these is true:

- task has an explicit issue/PR but the orchestrator has not yet seen a compact
  artifact;
- queue/backlog selection is needed;
- issue body, PR body, comments, labels, or checks would consume meaningful
  orchestrator context;
- artifact validation can be delegated;
- the next worker prompt can be drafted from bounded facts.

Use `secretary-pro` when one of these is true:

- `secretary-flash` returns `confidence:"low"`;
- the recommended route touches SDK/API/runtime/Compose/Langfuse/k8s;
- the task has multiple possible file reservations;
- several workers or waves are likely;
- artifacts disagree;
- the secretary artifact recommends GPT-5.5 or human review but no safety/user
  decision is actually needed;
- implementation would otherwise launch with incomplete decomposition.

Use GPT-5.5 orchestrator direct analysis only when:

- user/product/security/production authorization is required;
- launch/routing infrastructure itself is broken;
- secretary-pro reports unresolved contradiction;
- a bounded disputed slice must be inspected before a final decision.

## Artifact Contracts

Secretary workers write two primary artifacts:

```text
logs/SECRETARY.md
.signals/secretary-*.json
```

They may also write:

```text
logs/NEXT_WORKER_PROMPT.md
```

`SECRETARY.md` is for human-readable context:

- target and timestamp;
- method and commands;
- facts;
- risks;
- recommended route;
- suggested reserved files;
- focused checks;
- blockers/missing information;
- proposed next worker prompt path.

`SECRETARY.json` is the routing surface:

```json
{
  "status": "done|failed|blocked",
  "worker": "W-name",
  "mode": "secretary",
  "runner": "opencode",
  "agent": "secretary-flash|secretary-pro",
  "model": "opencode-go/deepseek-v4-flash",
  "task_kind": "queue_triage|issue_triage|pr_triage|decomposition|sdk_baseline|artifact_check|prompt_draft",
  "confidence": "low|medium|high",
  "summary": "1-3 lines",
  "facts": [],
  "risks": [],
  "recommended_route": {
    "next_worker_type": "secretary-pro|implementation|pr-review|review-fix|runtime-verify|blocked|finish",
    "agent": "secretary-pro|pr-worker|pr-review|pr-review-fix",
    "model": "provider/model",
    "contract": "quick|full",
    "reason": ""
  },
  "reserved_files": [],
  "focused_checks": [],
  "needs_user": [],
  "artifact_paths": {
    "markdown": "logs/SECRETARY.md",
    "prompt_draft": "logs/NEXT_WORKER_PROMPT.md"
  },
  "commands": [
    {"cmd": "command", "exit": 0, "status": "passed", "required": true, "summary": "short evidence"}
  ],
  "next_action": "launch_next_worker|ask_user|escalate|finish",
  "ts": "ISO-8601"
}
```

`NEXT_WORKER_PROMPT.md` is a draft. The orchestrator validates it, adjusts only
routing/metadata if needed, and launches the next worker. The draft is not
authority over safety gates.

## Acceptance Model

Current acceptance requires the orchestrator to inspect diffs. The new model:

1. Orchestrator validates schema, launch metadata, model route, prompt SHA,
   branch/base, artifact paths, reserved files, and command evidence.
2. Semantic diff review is delegated to a read-only PR review worker.
3. If review-fix changes the head SHA, launch a fresh PR review worker.
4. Orchestrator reads only compact review findings and disputed bounded slices.
5. No final success report without valid implementation and review artifacts.

This preserves rigor while moving token-heavy semantic reading out of the
orchestrator.

## SDK And Knowledge Freshness

The existing skill makes the orchestrator own `$sdk-research` and Context7.
The worker-first design changes the default:

- `secretary-flash` detects SDK/runtime risk and recommends escalation.
- `secretary-pro` or a dedicated research/docs worker produces the SDK/custom
  baseline.
- Orchestrator validates that the baseline is present, scoped, evidenced, and
  not `inconclusive`.
- Implementation workers consume the accepted baseline and block if it is
  insufficient.

Context7 and official docs remain scoped tools, not open-ended worker browsing.

## Launcher And Model Integrity

The prototype exposed a critical issue: launching `pr-review` with
`OPENCODE_MODEL=opencode-go/deepseek-v4-flash` still displayed DeepSeek V4 Pro
because the OpenCode agent frontmatter set `model: opencode-go/deepseek-v4-pro`.

Required launcher change:

- read selected agent frontmatter before launch;
- extract `model:`;
- fail if frontmatter model does not equal `OPENCODE_MODEL`, unless a future
  verified override mechanism proves the TUI uses the environment value;
- record both requested model and agent frontmatter model in launch metadata;
- add tests for mismatch rejection.

## File Changes

Expected skill package changes:

- `SKILL.md`
  - replace “Thin Orchestrator Rule” with “Worker-First Orchestrator Rule”;
  - add `secretary-flash` and `secretary-pro` default routes;
  - change default flow to secretary-first.
- `classification.md`
  - add `secretary_first`, `secretary_pro_escalation`, and `worker_chain`;
  - move complex decomposition to secretary-pro artifacts.
- `worker-contract.md`
  - add secretary artifact contracts;
  - add prompt draft rules.
- `references/worker-types.md`
  - add Secretary Flash and Secretary Pro sections.
- `references/review-verification.md`
  - move semantic diff review from orchestrator to review worker;
  - define bounded orchestrator inspection exceptions.
- `references/sdk-native.md`
  - move initial SDK baseline production to secretary-pro/research worker.
- `references/knowledge-freshness.md`
  - define delegated docs/research worker phases.
- `references/prompt-snippets.md`
  - add secretary prompt templates.
- `references/signal-schema.md`
  - add secretary schema or role-specific compact schema.
- `infrastructure.md`
  - document secretary agents and model integrity checks.
- `red-flags.md`
  - add red flags for orchestrator doing raw issue/code/diff analysis when a
    secretary worker should be used.
- `scripts/launch_opencode_worker.sh`
  - validate agent frontmatter model against requested model.
- `scripts/validate_worker_signal.py`
  - add `--role secretary`.
- `scripts/validate_worker_prompt.py`
  - validate secretary prompts.
- Tests
  - secretary artifact acceptance;
  - Flash/Pro route docs;
  - model mismatch rejection;
  - orchestrator-heavy phrases replaced or narrowed.

Expected OpenCode agent changes:

- `.opencode/agents/secretary-flash.md`
- `.opencode/agents/secretary-pro.md`

## Migration Plan

1. Add secretary agents and model mismatch validation.
2. Add secretary signal/prompt validation.
3. Update docs/contracts to introduce worker-first flow without removing
   existing worker roles.
4. Convert issue-audit/dependency-verify/artifact-check examples to secretary
   routes.
5. Update review-verification to require PR review worker semantic review.
6. Update SDK/knowledge freshness to delegate baseline production.
7. Run focused skill tests.
8. Run a live secretary-flash issue triage smoke.
9. Run a live secretary-pro decomposition smoke on a complex issue.

## Validation

Focused checks:

```bash
python3 -m pytest /home/user/.codex/skills/tmux-swarm-orchestration/tests -q
```

Live smoke checks:

```text
secretary-flash issue triage:
- OpenCode UI shows Secretary Flash / DeepSeek V4 Flash.
- Signal validates with --role secretary.
- Artifact recommends next route without raw transcript reading.

secretary-pro decomposition:
- OpenCode UI shows Secretary Pro / DeepSeek V4 Pro.
- Signal validates with --role secretary.
- Artifact includes reserved files, checks, and prompt draft.
```

## Risks

- Secretary artifacts may be plausible but incomplete. Mitigation: confidence,
  evidence commands, required route escalation on low confidence.
- More worker hops can increase wall-clock time. Mitigation: use Flash for cheap
  quick passes and Pro only when risk justifies it.
- Prompt drafts can drift from contract. Mitigation: prompt validator and
  orchestrator metadata correction only.
- Existing tests assert the old control-plane model. Mitigation: update tests
  intentionally with new worker-first contract.
- Model mismatch can silently waste money. Mitigation: launcher frontmatter
  model validation.

## Open Questions

- Should `secretary-pro` be allowed to update canonical docs in a docs-update
  phase, or should docs updates remain `pr-worker` with
  `project-docs-maintenance`?
- Should `secretary-flash` be the default for every explicit issue, or only
  when the issue body exceeds a small command budget?
- Should secretary artifacts be compact quick JSON, a new full schema, or both?
