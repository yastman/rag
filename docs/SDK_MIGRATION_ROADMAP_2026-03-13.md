# SDK Migration Roadmap (Post-Audit)

**As of:** 2026-03-13

## Phase 1: Cleanup Stale Audit Scope

- Mark already-shipped SDK items as done in issue #728.
- Remove/replace stale recommendations that are now misleading.
- Keep one canonical, tracked audit snapshot in `docs/`.

## Phase 2: High-ROI Incremental SDK Adoption

- Remove remaining runtime dependencies on deprecated `LLMService`.
- Simplify Langfuse prompt access toward SDK-native `get_prompt(...)` behavior and remove extra probe/cache complexity.
- Continue `PropertyBot` decomposition into domain routers/handlers.
- Keep aiogram-native patterns (`CallbackData`, `dp.errors`, workflow DI) as primary path.
- Keep `qdrant-client` and `redisvl` as the current keeper SDKs rather than reopening migration scope around them.

## Phase 3: Bounded SDK Spikes

- Langfuse experiment APIs for managed/offline evaluation workflows.
- Docling Python `DocumentConverter` native path behind a feature flag with contract-parity tests.
- `langchain-qdrant` only for apartment metadata-filter query prototype.

## Phase 4: Optional Research

- Presidio for higher-recall PII detection if required by product policy.
- NeMo Guardrails only with explicit policy needs and eval criteria.

## Guardrails

- No big-bang framework replacement.
- No extra Telegram orchestration layer on top of `aiogram` + `aiogram-dialog` without a demonstrated gap.
- Keep direct Qdrant SDK in main retrieval path unless parity on advanced features is demonstrated.
- Treat `Langfuse` eval/experiment work as a bounded spike first, not a repo-wide observability rewrite.
- Treat native `Docling` as opt-in until contract parity is proven against the HTTP path.
- Every migration task must have explicit acceptance criteria and rollback path.
