# План Issues Для Стабилизации Ядра

Статус: предлагается к старту выполнения
Дата: 2026-06-08
Источник:

- [`product-simplification-stage-0-decisions.md`](product-simplification-stage-0-decisions.md)
- [`monolith-core-audit-implementation-plan.md`](monolith-core-audit-implementation-plan.md)
- [`yaroslav-simplification-workflow.md`](yaroslav-simplification-workflow.md)

## Цель

Стабилизировать ядро ассистента и убрать лишнее из обязательного продуктового
пути без переписывания проекта и без раннего удаления опциональных поверхностей.

Главная проблема проекта сейчас:

```text
telegram_bot всё ещё владеет значимой частью RAG/runtime-логики,
а optional surfaces выглядят как обязательные для понимания и проверки продукта.
```

Целевое состояние:

```text
telegram_bot / E2E / optional API
  -> src.core.run_assistant_request()
  -> src.runtime owns classify/retrieve/generate/grounding/CRM proposal
  -> AssistantResult
```

Не цель текущего пакета:

- не удалять voice, Mini App, API, Langfuse, OTel, k8s или monitoring;
- не трогать production CRM write paths;
- не добавлять новые зависимости;
- не запускать установку зависимостей как часть обычной проверки;
- не делать большой PR «сделать монолит».

## Milestone

```text
Milestone: stabilize-core-monolith
```

Описание milestone:

```text
Make the assistant core the only product owner for text RAG requests:
contracts first, then grounding/generation/RAG ownership, then Telegram as a thin
adapter, then one core E2E proof. Optional platform surfaces stay optional until
core reliability is proven.
```

## Правила Выполнения

1. Один issue = один архитектурный шов.
2. Каждый issue имеет явный allowed write scope.
3. Не запускать `uv sync`, `pip install`, `npm install`, `docker build`,
   `docker compose up` без отдельного решения.
4. Для docs/plan PR использовать только лёгкие проверки:
   - `git diff --check`;
   - local Markdown link check через `python`, если нужно.
5. Для code PR запускать только focused checks, если окружение уже готово.
6. Не делать optional surfaces обязательными для core proof.
7. Любые CRM writes остаются только после HITL.

## Week 1 Focus

Цель первой недели — начать выполнение безопасно: стабилизировать public contract
ядра и вынести первую safety policy из Telegram ownership.

На этой неделе делаем:

1. `CORE-001`: Core contracts split.
2. `CORE-002`: Grounding policy canonical runtime home.
3. `CORE-003`: Runtime coupling ratchet design, если останется время.

На этой неделе не делаем:

- перенос всего `rag_pipeline()`;
- split `generate_response()`;
- переключение Telegram text path на core;
- изменения Docker/Compose/k8s;
- Langfuse/OTel optionalization beyond docs/contracts;
- live CRM writes.

## Backlog Overview

| Issue | Название | Lane | Риск | Блокирует | Основной результат |
|---|---|---|---|---|---|
| `CORE-001` | Core contracts split | Quick execution | Низкий | `CORE-004`, `CORE-005` | `src.core` имеет явный stable contract |
| `CORE-002` | Move grounding policy to runtime | Plan needed | Средний | `CORE-004`, `CORE-005` | Safety policy принадлежит `src.runtime` |
| `CORE-003` | Runtime coupling ratchets | Plan needed | Низкий | cleanup | Зафиксировать запрет dynamic `telegram_bot` coupling |
| `CORE-004` | Split generation core from Telegram rendering | Plan needed | Высокий | `CORE-005` | Core generation без Telegram `message` |
| `CORE-005` | Move RAG pipeline ownership to runtime | Plan needed | Высокий | `CORE-006` | Core больше не импортирует bot RAG path |
| `CORE-006` | Build runtime assistant pipeline | Plan needed | Средний | `CORE-007`, `CORE-008` | Real `run_assistant_pipeline()` returns `AssistantResult` |
| `CORE-007` | Core E2E golden path | Plan needed | Средний | optional cleanup | `make e2e-core-live` или accepted equivalent доказывает ядро |
| `CORE-008` | Telegram thin adapter rollout | Plan needed | Высокий | cleanup | Telegram вызывает core и рендерит `AssistantResult` |
| `CORE-009` | Optional surfaces status cleanup | Design first | Средний | docs cleanup | API/voice/miniapp/Langfuse/k8s явно optional |
| `CORE-010` | Shim cleanup and final docs | Plan needed | Средний | final | Удалены временные shims/flags после стабилизации |

## Issue Templates

### CORE-001: Core Contracts Split

```md
## Goal

Extract the public assistant core contracts into `src/core/contracts.py` without
changing runtime behavior.

## Lane

Quick execution.

## Why

Later migration issues need a stable request/result/dependency contract before
moving grounding, generation, RAG, or Telegram adapter code.

## Allowed Write Scope

- `src/core/contracts.py`
- `src/core/assistant.py`
- `src/core/__init__.py`
- `tests/unit/core/test_assistant_entrypoint.py`
- docs only if import paths need clarification

## Forbidden Scope

- Do not move `rag_pipeline()`.
- Do not move `generate_response()`.
- Do not change Telegram behavior.
- Do not touch Docker/Compose/k8s.
- Do not add dependencies.

## Tasks

- Move or re-export `UserContext`, `CoreDependencies`, `CrmAction`,
  `AssistantResult` from `src/core/contracts.py`.
- Add `AssistantRequest` as a first-class request object.
- Preserve current `run_assistant_request(query, *, collection, ...)` API.
- Keep skeleton mode behavior unchanged when dependencies are absent.
- Update unit tests for import compatibility and request id propagation.

## Acceptance Criteria

- Existing imports from `src.core` still work.
- `AssistantRequest` is available for future adapter/E2E code.
- No new `telegram_bot` imports are introduced under `src`.
- Runtime behavior is unchanged.

## Validation

Preferred if environment is already ready:

- `python -m pytest tests/unit/core/test_assistant_entrypoint.py -q`

If dependencies are not ready, do not install them automatically. Use:

- `git diff --check`
- static import inspection with `rg` / `python ast` only.
```

### CORE-002: Move Grounding Policy To `src.runtime.grounding`

```md
## Goal

Make grounding policy a runtime/core-owned module while preserving old Telegram
imports through a compatibility shim.

## Lane

Plan needed.

## Why

Grounding is safety/product policy, not Telegram UI. It controls strict mode,
safe fallback, legal-answer safety, and semantic cache reuse.

## Allowed Write Scope

- `src/runtime/grounding/__init__.py`
- `src/runtime/grounding/policy.py`
- `telegram_bot/services/grounding_policy.py`
- focused callers only if needed:
  - `telegram_bot/pipelines/client.py`
  - `telegram_bot/bot.py`
  - `telegram_bot/services/generate_response.py`
- focused grounding tests

## Forbidden Scope

- Do not change grounding thresholds or response text.
- Do not change generation prompt behavior.
- Do not change Telegram rendering.
- Do not move cache policy in this issue unless required for imports.

## Tasks

- Move the existing grounding functions to `src.runtime.grounding.policy`.
- Leave `telegram_bot/services/grounding_policy.py` as a deprecated re-export shim.
- Update safe internal callers to use the canonical `src.runtime` module.
- Add a focused test or static check proving old and new import paths expose the
  same functions.

## Acceptance Criteria

- Old import path remains compatible.
- New canonical import path works.
- Strict/no-data fallback behavior is unchanged.
- No new dependency install is required.

## Validation

Preferred if environment is already ready:

- focused grounding tests
- focused client pipeline grounding tests

No automatic dependency installation. At minimum:

- `git diff --check`
- `python` import/static check only if current environment can import project code
  without installing dependencies.
```

### CORE-003: Runtime Coupling Ratchets

```md
## Goal

Add or design lightweight guardrails that prevent `src.core` and `src.runtime`
from reintroducing runtime coupling to `telegram_bot`.

## Lane

Plan needed.

## Why

The static layering allowlist is empty, but dynamic string imports and default
factory specs can still point back to `telegram_bot`.

## Allowed Write Scope

- `tests/contract/*runtime*` or a new focused contract test
- `tests/data/*` only if an explicit allowlist is needed
- docs explaining temporary exceptions

## Forbidden Scope

- Do not break existing dynamic factory behavior before runtime replacements
  exist.
- Do not remove compatibility shims prematurely.

## Tasks

- Detect string literals under `src/core` and `src/runtime` that reference
  `telegram_bot.` in executable code.
- Decide temporary allowlist entries for documented transitional seams.
- Add a ratchet so the list can only shrink.

## Acceptance Criteria

- Current known transitional seams are explicit.
- New hidden dynamic coupling fails the contract.
- Docs distinguish static import compliance from runtime ownership.

## Validation

- `python` static check script or focused pytest if environment is ready.
- `git diff --check`.
```

### CORE-004: Split Generation Core From Telegram Rendering

```md
## Goal

Create a core generation service that does not accept Telegram `message` and does
not send/stream Telegram messages directly.

## Lane

Plan needed.

## Why

`generate_response()` currently mixes LLM answer generation, grounding fallback,
Langfuse/metrics hooks, formatting, and Telegram streaming concerns.

## Allowed Write Scope

- `src/runtime/generation/*`
- `telegram_bot/services/generate_response.py`
- focused generation/client pipeline tests

## Forbidden Scope

- Do not change prompts intentionally.
- Do not change user-visible answer formatting except where tests require a
  clearly documented adapter split.
- Do not remove Langfuse/metrics in this issue; only make them non-core if safe.

## Tasks

- Introduce `GenerationRequest` and `GenerationResult`.
- Move pure context formatting and fallback result shaping into runtime.
- Keep Telegram streaming in the Telegram wrapper.
- Preserve old `generate_response()` signature as a compatibility wrapper.

## Acceptance Criteria

- Core generation can be called without Telegram `message`.
- Old Telegram caller path remains compatible.
- Grounding fallback still works.
```

### CORE-005: Move RAG Pipeline Ownership To Runtime

```md
## Goal

Make the existing RAG pipeline canonical under `src.runtime` so `src.core` no
longer imports `telegram_bot.agents.rag_pipeline` dynamically.

## Lane

Plan needed.

## Why

RAG retrieval/cache/grade/rerank/rewrite is product runtime logic and should not
be owned by the Telegram adapter package.

## Allowed Write Scope

- `src/runtime/pipeline/*` or `src/runtime/retrieval/*`
- `telegram_bot/agents/rag_pipeline.py` compatibility shim
- `src/core/assistant.py`
- focused RAG/core tests

## Forbidden Scope

- Do not change retrieval algorithms.
- Do not change Qdrant schema.
- Do not change embedding provider behavior.
- Do not change Telegram UI.

## Tasks

- Move canonical implementation with minimal code changes.
- Leave old import path as shim.
- Switch `src.core.assistant` to canonical runtime module.
- Keep old function signature until adapter migration is complete.

## Acceptance Criteria

- `src.core.assistant` no longer references `telegram_bot.agents.rag_pipeline`.
- Legacy import path still works.
- RAG result shape is unchanged.
```

### CORE-006: Build Runtime Assistant Pipeline

```md
## Goal

Move live orchestration from `src.core.assistant` into
`src.runtime.pipeline.assistant_pipeline` while keeping `run_assistant_request()`
as the public wrapper.

## Lane

Plan needed.

## Why

`src.core` should expose the product API, while `src.runtime` owns the internal
classify/retrieve/generate/grounding/CRM proposal flow.

## Allowed Write Scope

- `src/runtime/pipeline/assistant_pipeline.py`
- `src/runtime/pipeline/contracts.py`
- `src/core/assistant.py`
- `src/core/contracts.py`
- `tests/unit/core/*`

## Forbidden Scope

- Do not switch Telegram adapter yet.
- Do not add new providers unless tests require them.
- Do not write to CRM.

## Tasks

- Introduce `run_assistant_pipeline(request, dependencies)`.
- Emit product logs with `request_id`.
- Return `AssistantResult` for success, cache hit, safe fallback, and dependency
  failure.
- Keep public `run_assistant_request()` compatible.

## Acceptance Criteria

- `src.core.assistant` has no dynamic `telegram_bot` imports.
- Runtime pipeline owns live orchestration.
- Errors are recoverable result objects with stable `error_type`.
```

### CORE-007: Core E2E Golden Path

```md
## Goal

Prove core product behavior through direct `run_assistant_request()` calls, not
through Telegram.

## Lane

Plan needed.

## Why

Reliability should be proven by user outcomes: prepared docs -> Qdrant -> core
request -> grounded answer checks.

## Allowed Write Scope

- `tests/e2e_core/*`
- `Makefile` only if target wiring is missing
- docs for local E2E usage

## Forbidden Scope

- Do not require Telegram.
- Do not require Langfuse/OTel.
- Do not require live CRM writes.

## Tasks

- Index synthetic docs into a test Qdrant collection.
- Call core directly.
- Assert retrieved docs, required facts, forbidden facts, missing-corpus behavior,
  and grounding fallback.
- Store lightweight artifacts for debugging.

## Acceptance Criteria

- One command or documented focused command proves the golden path.
- Telegram remains outside the main E2E gate.
```

### CORE-008: Telegram Thin Adapter Rollout

```md
## Goal

Route the main Telegram text path through `src.core.run_assistant_request()` and
render `AssistantResult` in Telegram.

## Lane

Plan needed.

## Why

Telegram is the production adapter, but it should not own core RAG/runtime logic.

## Allowed Write Scope

- `telegram_bot/bot.py`
- small adapter helper modules if needed
- focused Telegram adapter tests

## Forbidden Scope

- Do not change core contracts in this issue unless a blocker is found.
- Do not remove legacy branch until rollout is proven.
- Do not touch production CRM writes.

## Tasks

- Build `CoreDependencies` from existing bot runtime dependencies.
- Construct `UserContext` / `AssistantRequest` from Telegram state.
- Call `run_assistant_request()`.
- Render response text, sources, fallback/error states, and HITL action buttons.
- Use feature flag or shadow mode if risk is high.

## Acceptance Criteria

- Telegram text path can use core entrypoint.
- Adapter only renders and handles HITL confirmation.
- Rollback path exists until E2E and smoke checks are stable.
```

### CORE-009: Optional Surfaces Status Cleanup

```md
## Goal

Make optional surfaces explicit after the core golden path exists.

## Lane

Design first.

## Why

The project should not require voice, Mini App, API, Langfuse, OTel, k8s, or
monitoring to prove the core assistant path.

## Allowed Write Scope

- docs for API/voice/miniapp/Langfuse/k8s status
- small smoke checks only if needed

## Forbidden Scope

- Do not delete surfaces without explicit approval.
- Do not break active users.

## Tasks

- Mark each surface as required, optional, or archived candidate.
- Define a small smoke check for retained optional surfaces.
- Remove outdated docs that imply optional surfaces are required gates.

## Acceptance Criteria

- Core proof is documented as primary.
- Optional surfaces have clear status and do not block core release.
```

### CORE-010: Shim Cleanup And Final Docs

```md
## Goal

Remove temporary compatibility shims and feature flags after the runtime core path
is stable.

## Lane

Plan needed.

## Why

Shims are useful during migration but should not become permanent architecture.

## Allowed Write Scope

- old `telegram_bot/*` shim modules
- runtime contracts
- README/design docs
- focused import/path tests

## Forbidden Scope

- Do not remove a shim while any known caller still uses it.
- Do not remove rollback flags until Telegram adapter rollout is accepted.

## Tasks

- Find remaining shim imports.
- Switch callers to canonical `src.runtime` paths.
- Remove shims only when safe.
- Update architecture docs and final Definition of Done.

## Acceptance Criteria

- Dependency direction is enforced.
- Docs match code.
- Old bot-owned core path is gone or explicitly archived.
```

## First Execution Recommendation

Start with `CORE-001`. It is small, low-risk, and creates the stable contract
needed by every later issue.

Recommended branch:

```text
simplification/core-001-core-contracts
```

Recommended PR title:

```text
core: split assistant contracts
```

Recommended first implementation prompt:

```text
Implement CORE-001 only. Extract assistant contracts into src/core/contracts.py,
add AssistantRequest, preserve src.core public imports and run_assistant_request()
behavior, update focused core tests if possible, and do not touch Telegram,
RAG pipeline, generation, Docker, or dependencies.
```

## Follow-up Execution Slice: CORE-011 … CORE-018

Дата: 2026-06-08
Статус: accepted execution slice after `CORE-001` … `CORE-010` foundation.

| Issue | Название | Lane | Решение / результат |
|---|---|---|---|
| `CORE-011` / `#2394` | Remove PR Guardrails | Quick execution | Убрать PR-body guardrail job/template/script/tests, оставить быстрые static CI gates. |
| `CORE-013` / `#2396` | Trim obsolete guardrail tests | Quick execution | Удалить тесты, которые защищали удалённый PR-body gate, и оставить только lightweight reviewer fields. |
| `CORE-014` / `#2397` | Keep CI contract focused | Quick execution | Контракты CI проверяют lint/uv-lock/compose-config/secret-scan, но не требуют PR metadata policy. |
| `CORE-015` / `#2398` | Shrink Makefile live-core wiring | Quick execution | Вынести core live E2E command в shared `CORE_LIVE_PYTEST` и использовать `uv run --no-sync`. |
| `CORE-007` / `#2388` | Core live E2E golden path | Plan needed | Прямой `run_assistant_request()` остаётся защищённым live gate; artifacts пишутся локально для debug/release evidence. |
| `CORE-016` / `#2399` | Live E2E evidence hardening | Plan needed | Golden-case artifacts фиксируют query case, retrieved docs, route/error and response text without optional surfaces. |
| `CORE-018` / `#2403` | `create_agent` vs procedural core decision | Design first | Accepted ADR: core text RAG path is procedural; `create_agent` remains adapter/conversational shell only. |

Execution order:

1. `CORE-018` first: unblock `CORE-005`/`CORE-008` by accepting procedural
   core ownership in [`../adr/0019-core-text-path-procedural-runtime.md`](../adr/0019-core-text-path-procedural-runtime.md).
2. `CORE-011`/`CORE-013`/`CORE-014`: remove PR metadata policy from required CI
   so monolith PRs are not blocked by template-policy churn.
3. `CORE-015`: make `e2e-core-live` use the existing environment via
   `UV_RUN_NO_SYNC`, not an implicit dependency sync.
4. `CORE-007`/`CORE-016`: keep real reliability proof in the live core E2E path
   and store local artifacts from the synthetic corpus.
