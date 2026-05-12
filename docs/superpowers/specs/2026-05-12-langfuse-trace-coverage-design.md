# Langfuse Trace Coverage Design

## Context

GitHub issue `#1307` tracks local Langfuse bring-up and bot trace coverage.
The latest audit shows that local Langfuse, LiteLLM, Qdrant, BGE-M3, and the
Telegram E2E runner can run, but `#1307` is still not acceptable because the
core trace contract fails.

The current hard failure is tracked in `#1485`: required text scenarios receive
Telegram responses, but Langfuse validation reports missing root output,
missing cache-check coverage, and missing required scores. Open PR `#1491`
addresses one part of that failure by accepting `cache-check` as a product
equivalent alias for `node-cache-check` in the E2E validator.

This design keeps the full `#1307` goal visible, but scopes the first
implementation phase to `#1485` after accounting for `#1491`.

## Goals

- Close the current core text trace gap without introducing a custom
  observability transport.
- Keep Langfuse integration SDK-first:
  - `start_as_current_observation` for app-owned roots;
  - `@observe` for child observations;
  - `propagate_attributes` for trace attributes;
  - SDK trace I/O helpers for sanitized root input/output;
  - `create_score` through the existing scoring helper for required scores.
- Make the `#1307` acceptance path explicit across follow-up issues.
- Keep implementation phases small enough to verify independently.

## Non-Goals

- Do not replace Langfuse with another observability layer.
- Do not count LiteLLM proxy-owned `litellm-acompletion` traces as application
  coverage.
- Do not solve voice fixture, mini-app health, Qdrant data preflight, and
  latest-trace audit artifact work inside the first `#1485` phase.
- Do not access VPS, production, secrets, SSH, cloud credentials, or real CRM
  write paths.

## Current-State Findings

### Issue Status

- `#1307` remains open and cannot be closed yet.
- `#1485` is the current hard blocker for required text scenarios.
- `#1486` blocks voice-note scenario `8.1` because `E2E_VOICE_NOTE_PATH` is not
  available.
- `#1487` blocks `make validate-traces-fast` because `mini-app-frontend` is
  unhealthy in the current compose path.
- `#1488`, `#1489`, and `#1490` cover Qdrant preflight, product-meaningful
  Telethon assertions, and post-E2E latest-trace audit artifacts.
- PR `#1491` is clean and narrowly fixes validator aliasing for
  `cache-check`/`node-cache-check`.

### Existing SDK Surfaces

- `telegram_bot/middlewares/langfuse_middleware.py` owns the app-level
  `telegram-message` root using `start_as_current_observation` and
  `propagate_attributes`.
- `telegram_bot/bot.py` owns `telegram-rag-query` and
  `telegram-rag-supervisor` child observations.
- `telegram_bot/pipelines/client.py` and `telegram_bot/agents/rag_pipeline.py`
  emit child observations for deterministic pipeline and RAG stages.
- `telegram_bot/services/telegram_formatting.py` already records sanitized
  response output through the SDK when responses are sent.
- `telegram_bot/scoring.py` centralizes score writes through explicit
  `trace_id` usage.
- `scripts/e2e/langfuse_trace_validator.py` validates root input/output,
  required observations, and required scores for Telethon scenarios.

### Trace Contract

The core E2E validator requires these score names for text scenarios:

- `query_type`
- `latency_total_ms`
- `semantic_cache_hit`
- `embeddings_cache_hit`
- `search_cache_hit`
- `rerank_applied`
- `rerank_cache_hit`
- `results_count`
- `no_results`
- `llm_used`

The root trace must contain sanitized input with `query_hash` and sanitized
output with `answer_hash`. The validator should treat app-owned
`telegram-message` traces as authoritative and ignore flat LiteLLM proxy traces
for app coverage.

## Recommended Approach

Use a phased `#1307` design with Phase 1 scoped to `#1485`.

This is better than a narrow `#1485`-only design because the project retains one
clear acceptance path for `#1307`. It is also safer than a one-shot `#1307`
implementation because voice fixtures, Docker health, Qdrant readiness, and
trace audit artifact work have different failure modes and should not be mixed
into one PR.

## Architecture

### App-Owned Root Trace

`LangfuseContextMiddleware` remains the root owner for Telegram updates. It
creates `telegram-message` or `telegram-rag-voice` observations via the native
SDK and propagates session, user, and tags through `propagate_attributes`.

The root trace must contain:

- sanitized input from `build_safe_input_payload`;
- sanitized output from `build_safe_output_payload`;
- no raw Telegram message, chat, user, CRM, or credential payloads.

### Child Observations

Child work remains observation-first:

- request handler: `telegram-rag-query`;
- supervisor path: `telegram-rag-supervisor`;
- deterministic pipeline: `client-direct-pipeline`;
- RAG pipeline: `rag-pipeline`, `cache-check`, retrieval, grading, rerank,
  generation, cache-store;
- graph/voice path: `node-*` spans and `transcribe` where exercised.

No new wrapper should hide Langfuse SDK v4 semantics. If a code path needs a
span, it should use `@observe` or `start_as_current_observation`.

### Scores

Required scores stay centralized in `write_langfuse_scores`. Runtime paths that
return a user-visible answer must call it with the app-owned current trace id.

Early-return and degraded paths should still write the same required score set
with safe defaults when the bot sends a response. This keeps validators
deterministic and avoids treating missing metrics as successful degradation.

## Data Flow

For required text scenarios `0.1`, `6.3`, and `7.1`:

1. Aiogram update enters `LangfuseContextMiddleware`.
2. Middleware creates root `telegram-message` with sanitized input.
3. `handle_query` creates `telegram-rag-query`.
4. `_handle_query_supervisor` creates `telegram-rag-supervisor`.
5. The deterministic or agent RAG path emits pipeline observations through
   `@observe`.
6. The Telegram sender records sanitized root output containing `answer_hash`.
7. The pipeline writes required scores on the same trace id.
8. The E2E validator fetches the app-owned trace and validates root I/O,
   observations, and scores.

The validator must not infer application coverage from `litellm-acompletion`.
Those traces are proxy-owned and can remain flat.

## Error Handling And Gates

### Phase 1 Scenario Matrix

Phase 1 applies to the required text scenarios in `make e2e-test-traces-core`.
It does not apply to voice scenario `8.1` until Phase 2 provides the fixture.

| Scenario | Scenario kind | Required root | Required observations | Required scores | Cache-check rule |
|---|---|---|---|---|---|
| `0.1` Digital Nomad visa basics | `text_rag` | `telegram-message` input has `query_hash`; output has `answer_hash` | `telegram-rag-query`, `telegram-rag-supervisor` | full core E2E score set | required unless the scenario is explicitly classified as chitchat/off-topic, which this scenario is not |
| `6.3` Complex query | `text_rag` | `telegram-message` input has `query_hash`; output has `answer_hash` | `telegram-rag-query`, `telegram-rag-supervisor` | full core E2E score set | required unless the scenario is explicitly classified as chitchat/off-topic, which this scenario is not |
| `7.1` No results | `fallback` in runner mapping, but still user-visible Telegram RAG text flow | `telegram-message` input has `query_hash`; output has `answer_hash` | `telegram-rag-query`, `telegram-rag-supervisor` | full core E2E score set | required when the authoritative `query_type` score is non-zero |

The cache-check requirement is satisfied by either `node-cache-check` or
`cache-check`. This is an observation-name compatibility rule only; scores and
root I/O remain strict and are not aliased.

Cache-check condition formula for Phase 1:

1. If the `query_type` score is present, it is authoritative.
2. `query_type == 0.0` means chitchat/off-topic and does not require
   cache-check.
3. Any other numeric `query_type` value means a non-chitchat text path and
   requires cache-check.
4. If the `query_type` score is missing, non-numeric, or unparsable, validation
   must fail as a missing or invalid required score. Branch logic may fall back
   to scenario hints for diagnostic output only, but that fallback must not make
   the scenario pass.

### Phase 1 Hard Failures

Phase 1 fails when a required text scenario has:

- missing `query_hash` on root input;
- missing `answer_hash` on root output;
- missing `telegram-rag-query` or `telegram-rag-supervisor`;
- missing required score names;
- missing cache-check equivalent when the authoritative `query_type` score is
  present and non-zero.

The cache-check equivalent can be either `node-cache-check` or `cache-check`
after `#1491` lands or is otherwise incorporated.

### Phase 1 Non-Blockers

Phase 1 should not fail because of:

- flat `litellm-acompletion` traces;
- missing LiveKit `voice-session`;
- missing voice-note scenario `8.1` while `#1486` is open;
- `mini-app-frontend` health while `#1487` is open;
- missing post-E2E latest-trace artifact while `#1490` is open.

Phase 1 must use a text-only E2E invocation instead of the current full
`make e2e-test-traces-core` target because that target includes voice scenario
`8.1`. The deterministic Phase 1 runtime gate is:

```bash
E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1
```

The full `make e2e-test-traces-core` target becomes a required gate only after
Phase 2 resolves `#1486`.

### Score Enforcement Decision

Phase 1 score enforcement belongs in `scripts/e2e/langfuse_trace_validator.py`
and its unit tests. That validator checks the exact trace produced by a
Telethon scenario, so it can fail `make e2e-test-traces-core` on missing
scenario-level scores without conflating unrelated local trace history.

`make validate-traces-fast` should not enforce score presence in Phase 1. It
should keep its current role as a broad runtime-family and root-context gate
until Phase 3 or a dedicated follow-up extends it to sampled score coverage.
That future extension must be planned separately because it changes the
go/no-go behavior of a broader compose validation target.

### Blocked Runtime Behavior

If the bot sends a user-visible response, root output and required scores must
exist. If an external dependency prevents a response, the gate should report a
clear blocked/error reason instead of silently counting the scenario as covered.

## Implementation Phases

### Phase 1: Core Text Trace Contract (`#1485`)

- Review and merge, or reproduce, PR `#1491` for cache-check aliasing.
- Verify all user-visible text response paths record sanitized root output with
  `answer_hash`.
- Verify all user-visible text paths call `write_langfuse_scores` with the
  active app-owned trace id.
- Add unit tests for:
  - missing root output fails validation;
  - missing required scores fail validation;
  - `cache-check` satisfies `node-cache-check` where appropriate.
- Run focused unit tests for the validator, formatting root output, scoring, and
  trace contract.
- Run the text-only E2E trace gate when local credentials and services are
  available:
  `E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1`.
- Do not use full `make e2e-test-traces-core` as a Phase 1 pass/fail gate while
  `#1486` is open, because it includes voice scenario `8.1`.

### Phase 2: Voice Fixture (`#1486`)

- Provide or document a local ignored voice-note fixture path.
- Ensure scenario `8.1` can send a Telegram voice note safely.
- Validate `telegram-rag-voice`, `transcribe`, voice scores, and sanitized root
  output.

### Phase 3: Fast Trace Validation Runtime (`#1487`)

- Fix or scope `validate-traces-fast` so unrelated mini-app frontend health does
  not block Langfuse trace validation.
- Decide and implement any sampled score coverage for `validate-traces-fast`
  only in this phase or a separate follow-up, not in Phase 1.
- Preserve compose-supported commands and local-only constraints.

### Phase 4: Qdrant Data Preflight (`#1488`)

- Add a preflight that detects missing or unsuitable Qdrant test data before
  Telethon trace scenarios run.
- Fail with an actionable local-only message instead of producing misleading
  trace gaps.

### Phase 5: Product-Meaningful Scenarios (`#1489`)

- Strengthen Telethon scenario assertions so text RAG, apartment/catalog search,
  and no-results paths verify product meaning, not only that the bot responded.
- Keep judge-free core trace gates deterministic where possible.

### Phase 6: Latest-Trace Audit Artifact (`#1490`)

- Add a post-E2E audit loop that reads latest Langfuse traces and records a
  redacted artifact with trace ids, observed families, scores, and missing gaps.
- Keep the artifact local-safe and free of secrets, raw Telegram payloads, and
  CRM identifiers.

## Testing Strategy

### Unit Tests

- `tests/unit/e2e/test_langfuse_trace_validator.py` for root output, score
  requirements, and observation alias behavior.
- `tests/unit/test_telegram_formatting.py` for SDK root output writes through
  the Telegram sender.
- `tests/unit/pipelines/test_client_pipeline.py` and scoring tests for required
  score writes on handled text paths.
- Contract tests for trace family declarations when contract metadata changes.

### Runtime Validation

For Phase 1:

- `uv run pytest tests/unit/e2e/test_langfuse_trace_validator.py -q`
- focused formatting/scoring tests affected by implementation;
- `E2E_VALIDATE_LANGFUSE=1 uv run python scripts/e2e/runner.py --no-judge --scenario 0.1 --scenario 6.3 --scenario 7.1`
  when local Telegram credentials and Langfuse stack are available.

For full `#1307`:

- `make local-up`
- `make docker-ml-up`
- `make bot`
- `make e2e-test-traces-core`
- `make validate-traces-fast`
- latest-trace audit command from Phase 6

Skipped checks must be stated with the exact blocker issue or missing local
credential/artifact.

## Rollout

Use small PRs aligned to the phase list:

1. `#1485` text trace contract.
2. `#1486` voice fixture.
3. `#1487` fast validation runtime.
4. `#1488` Qdrant data preflight.
5. `#1489` product-meaningful E2E assertions.
6. `#1490` latest-trace audit artifact.

Do not close `#1307` until the required local flow can show:

- local Langfuse health;
- Telethon readiness;
- text RAG, complex, no-results, and voice scenarios accounted for;
- required app-owned trace roots and child observations;
- required scores attached to app-owned traces;
- documented blockers only for explicitly non-required optional surfaces.

## Open Questions

- Whether `#1491` should be merged as-is before Phase 1 implementation or
  folded into a broader `#1485` PR.
- Whether `validate-traces-fast` should eventually enforce score presence on
  sampled `telegram-message` roots. Phase 1 does not decide this beyond keeping
  score enforcement in the Telethon E2E validator.
