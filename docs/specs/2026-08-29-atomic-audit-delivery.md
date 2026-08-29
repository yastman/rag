# Atomic Audit Delivery Specification

Date: 2026-08-29
Repository: `yastman/rag`
Executable issue range: `#3199` through `#3245`
Parent indexes: `#3197` (presentation) and `#3198` (simplification)

## Outcome

Restore a reproducible five-minute real-estate presentation first, then simplify the runtime and update dependencies without mixing unrelated work. Every executable GitHub issue is an independently reviewable and recoverable delivery unit.

The delivery invariant is:

```text
one executable issue
  -> one codex/issue-<number>-<slug> branch
  -> one .worktrees/issue-<number> worktree
  -> one issue-specific specification and implementation plan
  -> one pull request targeting dev
  -> one verified merge into origin/dev
```

No pull request may close or implement more than one executable issue. Parent issues `#3197` and `#3198` remain indexes and receive no bundled implementation. Neither parent may close prematurely: `#3197` closes only after all eight presentation children satisfy its acceptance evidence, and `#3198` closes only after every scheduled child is closed with evidence or explicitly descoped and the final presentation and delivery gates pass.

## Product Boundary

The presentation spine is deliberately small:

```text
Telegram event
  -> deterministic root menu / FSM / human-handoff gate
  -> ApartmentCatalog -> Qdrant apartments
     or
     KnowledgeAnswer -> assistant-core -> canonical RAG -> Qdrant knowledge
  -> one Telegram presentation response

Redis = polling ownership, fail-open caches, and optional handoff state
BGE = knowledge embedding and reranking
LiteLLM = provider adapter/router, not orchestration
```

The target does not add OpenAI Agents SDK. The audited application has no live model-driven tool loop, stable LiteLLM still owns multi-provider fallback, and the current stable `openai-agents`/LiteLLM dependency requirements are incompatible. The cleanup target is direct SDK/service boundaries, not a replacement agent harness.

## Candidate Frozen by #3201

| Evidence | Value |
| --- | --- |
| Remote candidate / rollback SHA | `72bf7da1838ccee6496febf37e3976572273013d` |
| Candidate source | exact fetched `origin/dev` |
| Branch | `codex/issue-3201-freeze-demo-candidate` |
| Worktree | `C:\Dev\projects-wsl-migrated-2026-07-13\rag-fresh\.worktrees\issue-3201` |
| Tracked worktree state before documentation | clean |
| Primary checkout | `C:\Dev\projects-wsl-migrated-2026-07-13\rag-fresh` |
| Preserved primary state | local `dev@dc8ed78cf48dea84fa7958f4285caa097b4b5506`; user-owned `.gitignore` modification left untouched |
| Worktree ignore rule | `.gitignore` already contains `.worktrees/` |

The rollback point for every subsequent issue is the `origin/dev` commit from which that issue's worktree is created. A dependent issue starts only after every predecessor is merged and a fresh fetch proves those merge commits are ancestors of its new base.

## Windows Static Preflight Baseline

The read-only static preflight completed far enough to validate the repository and Compose configuration, but correctly exited `1` because operator paths still point to Linux locations:

- `BGE_M3_ONNX_MODEL_HOST_DIR=/home/user/projects/rag-fresh/logs/bge_m3_onnx_int8` does not exist on the Windows host and model artifacts are absent.
- `GDRIVE_SYNC_DIR=/opt/rag-fresh/drive-sync` does not exist on the Windows host.
- Git reports `core.symlinks=false`; this is a warning, not a secret or data mutation.
- `uv`, Docker, Git, all three lock authorities, Python 3.12.12, native NTFS placement, and `docker compose config` passed.

The preflight used the operator environment file only as input. No secret values are recorded here. Fixing operator paths or starting shared services is outside `#3201`.

## Dependency DAG

The table records hard predecessors named by executable issue bodies. A dash means that the issue has no hard GitHub predecessor, not that it should outrank the presentation.

### Presentation contract

| Issue | Hard predecessors |
| --- | --- |
| `#3199` Redis polling/cache contract | — |
| `#3200` grounded Q&A and safe no-answer | — |
| `#3201` clean recoverable candidate | — |
| `#3202` readiness for both Qdrant collections and data | —; schedule after `#3203` so readiness inspects the shipped seed |
| `#3203` truthful apartment seed and prompts | — |
| `#3204` deterministic Ask/FAQ/root-menu FSM | `#3200`, `#3202`, `#3203` |
| `#3205` automated five-minute Telegram gate | `#3199`–`#3204` |
| `#3206` three rehearsals and exact runbook | `#3205` |

Presentation work is the first milestone. The initial independent discovery/implementation wave after `#3201` is `#3199`, `#3200`, and `#3203`; `#3202`, `#3204`, `#3205`, and `#3206` follow their evidence.

### Runtime and orchestration simplification

| Issue | Hard predecessors |
| --- | --- |
| `#3207` move live graph-named helpers | `#3200` |
| `#3208` converge Telegram Q&A on assistant-core | `#3200` |
| `#3209` remove unused semantic/analyzer router | `#3200` |
| `#3210` unify Telegram manifest/lock authority | — |
| `#3211` delete dormant LangGraph history/HITL island | — |
| `#3212` delete unwired HTTP wrapper | — plus deployment proof |
| `#3213` stop false viewing confirmations | `#3204` |
| `#3214` remove inactive Qdrant conversation history | — |
| `#3215` remove disabled client-direct pipeline | `#3208` |
| `#3216` remove `ImperativeBotAgent` and inert tools | `#3204`, `#3208` |
| `#3217` delete duplicate agent RAG | `#3216` |
| `#3218` remove no-op checkpointer/retry plumbing | `#3211`, `#3216` |
| `#3219` delete bot-local duplicate RAG policies | `#3208`, `#3217` |
| `#3220` retire graph compatibility and factory | `#3207`, `#3208`, `#3212` |
| `#3221` remove LangGraph/LangChain/LangSmith | `#3207`, `#3211`, `#3212`, `#3220` |
| `#3222` collapse Telegram generation compatibility | `#3208`, `#3215`, `#3216` |
| `#3223` use a native LiteLLM SDK boundary | `#3222` |
| `#3224` native structured apartment gap-fill | `#3203`, `#3223` |

`#3218` must preserve the Redis contract established by `#3199`; its issue body records that compatibility requirement separately from its hard `Blocked by` predecessors.

### Dependency cohorts

| Issue | Hard predecessors |
| --- | --- |
| `#3225` aiogram 3.31 cohort | `#3204`, `#3210` |
| `#3226` RedisVL 0.26 / redis-py `<8` | `#3199`, `#3210` |
| `#3227` LiteLLM 1.98 / OpenAI 2.54 | `#3210`, `#3221`, `#3223` |
| `#3228` Pydantic/settings cohort | `#3210`, `#3221` |
| `#3229` qdrant-client 1.19 | `#3202`, `#3210` |
| `#3230` root BGE FastAPI compatibility | `#3210`, `#3228` |
| `#3231` Redis server 8.10.1 | `#3226` |
| `#3232` Qdrant server 1.19 | `#3202`, `#3229` |
| `#3233` BGE sidecar web stack | `#3228`, `#3230` |
| `#3234` BGE sidecar ML stack | `#3233` |
| `#3235` Docling ingestion cohort | `#3221`, `#3226`, `#3227`, `#3228`, `#3229`, `#3230` |
| `#3236` development tools only | `#3221`, `#3225`–`#3230`, `#3235` |

All issues that modify the same manifest/lock authority are serialized even when the graph would otherwise permit parallel work. Redis and Qdrant image updates may be prepared independently, but their shared Compose files make their write/merge windows serial.

### Product honesty and concrete tooling debt

| Issue | Hard predecessors |
| --- | --- |
| `#3237` retire legacy Voyage apartment indexing | `#3202`, `#3203` |
| `#3238` one `ApartmentCatalog` interface | `#3202`, `#3203`, `#3204` |
| `#3239` capability-gate Forum handoff | `#3199`, `#3204` |
| `#3240` optional voice with text fallback | `#3203`, `#3204` |
| `#3241` capability-gate bookmarks/PostgreSQL | `#3204` |
| `#3242` executable benchmark contract or deletion | — |
| `#3243` tracked duplicate-test-name ratchet | — |
| `#3244` real unified-ingestion e2e or deletion | — |
| `#3245` single import-linter authority | — |

The no-predecessor tooling issues are independent but remain lower priority than the presentation. `#3245` should merge before the final development-tool lock refresh in `#3236` to avoid validating two import-linter authorities.

## Per-Issue Delivery Protocol

For each executable issue:

1. Fetch and prune `origin`; confirm the issue is open and no equivalent PR already exists.
2. Prove every hard predecessor is merged into `origin/dev`.
3. Create `codex/issue-<number>-<slug>` from the exact fresh `origin/dev` SHA in `.worktrees/issue-<number>`.
4. Add an issue-specific specification and checkbox implementation plan. Record owned files, non-goals, rollback, test evidence, and any stateful prerequisite.
5. Write or tighten the failing characterization/contract first for behavior changes. Documentation-only or operational issues use command evidence instead of an artificial unit test.
6. Implement only that issue and run its narrowest focused gate. Run the scoped repository gate required by `AGENTS.md` after focused tests pass.
7. Inspect the complete diff and obtain independent correctness/security and simplicity review when relevant.
8. Commit only owned changes, push the issue branch, and open one PR targeting `dev` with `Closes #<number>` plus exact verification output.
9. Merge only when required local gates and PR checks are green. Fetch `origin` and prove the tested commit/merge is in `origin/dev`.
10. Attach evidence to the issue, close it if GitHub did not, then safely remove that exact worktree and branch. Never clean another issue's worktree.

Parallel agents may inspect or implement independent issues only when they have distinct worktrees and one writer owns each file set. Main serializes shared locks, Compose files, integration verification, PR creation, and merges.

## Verification and Rollback

- Documentation/operational work: Git identity, clean-status, ancestry, preflight, and secret-scan evidence.
- Core/runtime work: narrow failing test first, then `make test-core`.
- Adapter/service work: `make test-core`, then `make test` after focused tests.
- Contract work: `make test-contract` after focused contracts.
- Candidate delivery: `make candidate-check` at the appropriate milestone; `make test-full` only for the manual final pre-merge/final-epic proof required by the runbook.
- Stateful image changes: fresh and populated service cases, snapshot/backup proof, old immutable image digest, and an exercised rollback path.

If an issue fails, preserve its branch/worktree and report the blocker. Do not merge partial behavior, rewrite `dev`, or advance descendants. Reverting one accepted issue or redeploying its recorded predecessor SHA is the default code rollback; stateful issues additionally use their issue-specific snapshot procedure.

## Non-Goals

- No broad all-dependencies update.
- No OpenAI Agents SDK, OpenAI SDK 3.x, redis-py 8.x, or invented orchestration requirement.
- No consolidation of the knowledge and apartment Qdrant collections.
- No committed credentials, production customer data, fabricated listings/photos, or destructive repair of shared services.
- No combining “small” issues into one branch or PR.
- No counting the Ponytail audit's gross deletion ceiling as realized savings; only merged diffs count.
