# Exhaustive List Coverage for Knowledge RAG

Date: 2026-03-25
Status: Approved design
Scope: Telegram knowledge/RAG answer path only

## Summary

The current knowledge RAG path under-answers enumeration-style questions such as "какие еще есть виды" or "напиши полный список". The root cause is primarily generation policy, not missing source data:

- retrieval already finds relevant chunks containing multiple valid variants
- the current Langfuse `generate` prompt strongly optimizes for brevity
- top retrieval results can be dominated by chunks from one source document

The fix should be delivered in two small rollouts:

1. Add `needs_coverage` plus a dedicated Langfuse prompt path `generate_exhaustive_list`
2. Add coverage-oriented retrieval grouping in Qdrant for this mode

MMR is explicitly deferred unless grouping alone proves insufficient.

## Problem Statement

For questions that imply exhaustive enumeration, the current system often returns only the first one or two variants even when retrieval contains more.

Observed failure mode:

- top retrieved chunks contain the expected answers
- the first chunk often starts with the first visible option, biasing generation
- the current prompt instructs the model to be short, avoid listing everything, and keep responses visually compact

As a result, the user gets a polished but incomplete answer.

## Goals

- Return fuller answers for enumeration-style knowledge questions
- Preserve current behavior for normal concise knowledge questions
- Keep rollout risk low by separating generation policy changes from retrieval diversification
- Add observability so coverage mode can be measured and tuned safely

## Non-Goals

- No redesign of the entire RAG pipeline
- No global intent framework for every bot LLM feature
- No new LLM classifier for coverage detection
- No MMR-enabled full reranking pipeline in the first two PRs
- No changes to apartment search, CRM flows, voice-specific prompts, or unrelated agents

## Current State

### Generation

The active knowledge generation path is `telegram_bot.services.generate_response.generate_response`.

Current behavior:

- uses `generate` prompt from Langfuse when style mode is off
- allows prompt config overrides such as `temperature` and `max_tokens`
- applies response-style logic before final prompt assembly

Current prompt policy is optimized for short Telegram responses and conflicts with exhaustive-list questions.

### Retrieval

The active retrieval path is `telegram_bot.graph.nodes.retrieve.retrieve_node`.

Current behavior:

- retrieves hybrid results via Qdrant
- can use ColBERT server-side reranking when query vectors are available
- does not apply grouping in the default path
- does not apply MMR in the default path

This allows several chunks from the same source document to dominate the final context.

## Design Overview

The design introduces a narrow knowledge-RAG-only coverage mode.

Coverage mode is activated when the question strongly implies exhaustive enumeration. When active:

- generation routes to a dedicated Langfuse prompt policy
- retrieval prefers document diversity over raw top-k chunk dominance
- observability records whether the mode was used and how much source diversity reached generation

The mode is intentionally explicit and limited in scope.

## Rollout 1: Coverage-Aware Generation

### New runtime signal

Add a boolean flag:

- `needs_coverage: bool`

Optional internal normalized intent name:

- `exhaustive_list`

This signal is used only in the knowledge/RAG path in the first rollout.

### Detection strategy

Detection should be deterministic and cheap. Use rule-based heuristics, not an LLM classifier.

Starting trigger patterns:

- `какие виды`
- `какие варианты`
- `какие еще есть`
- `полный список`
- `перечисли все`
- `все основания`
- `все способы`

The detector should bias toward precision over recall at first. False negatives are acceptable in rollout 1. False positives are more dangerous because they will expand answers unexpectedly.

### Prompt routing

When `needs_coverage` is false:

- preserve existing prompt selection behavior

When `needs_coverage` is true:

- bypass the concise prompt path
- fetch a separate prompt from Langfuse using prompt name `generate_exhaustive_list`

Important constraint:

- use prompt name for task routing
- keep Langfuse labels for environment and experiment routing, not task semantics

This matches Langfuse prompt versioning guidance. Prompt names should represent distinct task contracts, while labels should remain suitable for `production`, `staging`, or experimental rollout labels.

### Prompt contract for `generate_exhaustive_list`

The new prompt should:

- explicitly enumerate all relevant variants found in context
- group closely related variants
- remove duplicates and near-duplicates
- prefer completeness over brevity
- state clearly when the answer is limited to what is found in the knowledge base

The prompt should not include constraints such as:

- no more than 4 items
- keep response within 450-700 characters
- do not list everything

The prompt should still preserve:

- grounding to context only
- same-language response behavior
- concise honesty when the base is incomplete

### Precedence over response style

Coverage mode must override short/balanced/detailed response style routing. Otherwise the existing style contract will keep shrinking exhaustive answers.

Rule:

- if `needs_coverage=true`, use `generate_exhaustive_list`
- only if `needs_coverage=false`, allow normal response-style prompt routing

### Observability additions

Add span metadata for:

- `needs_coverage`
- `coverage_mode`
- `prompt_name`
- `prompt_source`
- `prompt_version`
- `distinct_doc_count`
- `documents_count`
- `answer_chars`
- `answer_words`

If practical, also log a cheap completeness proxy such as:

- `answer_list_item_count`

This rollout should make prompt behavior measurable before retrieval changes begin.

## Rollout 2: Coverage Retrieval in Qdrant

### Goal

Reduce context domination by one document when coverage mode is active.

### Retrieval strategy

Only for `needs_coverage=true`, switch from ordinary retrieval to coverage retrieval.

Coverage retrieval behavior:

- widen the candidate pool
- prefer unique source documents
- limit per-document chunk dominance
- keep implementation compatible with the existing Qdrant query path

### Primary mechanism: grouping

Use Qdrant grouping by document identifier where available.

Initial parameters:

- `group_by=document_id` or stable equivalent payload field
- `group_size=2`
- `final_limit=10`
- widened candidate pool around `40`

Why grouping first:

- it directly targets the observed failure mode
- it matches Qdrant guidance for chunked-document search
- it has a smaller blast radius than introducing MMR immediately

### Fallback mechanism: post-query cap

If a stable `document_id` field is not consistently present in payloads, apply a local fallback cap after retrieval:

- keep at most 2-3 chunks per logical document

This fallback should be deterministic and preserve original ranking order as much as possible.

### MMR policy

MMR should not be enabled by default in rollout 2.

Enable MMR only if post-grouping analysis still shows:

- too few unique source documents
- many near-duplicate chunks from different documents
- insufficient coverage on the golden enumeration set

If MMR is introduced later, it should run on an already widened candidate pool and be guarded by observability.

## Data Flow

### Normal knowledge question

1. detect `needs_coverage=false`
2. run normal retrieval
3. run normal prompt routing
4. generate concise answer

### Enumeration-style knowledge question

1. detect `needs_coverage=true`
2. run coverage retrieval
3. route to `generate_exhaustive_list`
4. generate coverage-oriented answer

## File-Level Change Plan

### Rollout 1

- `telegram_bot/services/generate_response.py`
  - integrate `needs_coverage`
  - route to `generate_exhaustive_list`
  - give coverage mode priority over style mode
  - add observability fields
- `telegram_bot/integrations/prompt_manager.py`
  - no contract change required, but reuse prompt/version metadata cleanly
- optional small helper file or local helper in generation path
  - heuristic detector for enumeration-style requests

### Rollout 2

- `telegram_bot/graph/nodes/retrieve.py`
  - branch into coverage retrieval mode when `needs_coverage=true`
- `telegram_bot/services/qdrant.py`
  - expose grouping-friendly retrieval parameters in the active API
  - add observability for grouping results and distinct documents
- optional helper for post-query per-document capping if payload grouping is not stable

## Validation Plan

### Golden set

Create a focused golden set of coverage questions, for example:

- `какие виды`
- `какие варианты`
- `какие еще есть`
- `полный список`
- `перечисли все`
- `все основания`

The golden set should be specific to knowledge-base coverage questions, not mixed into generic QA-only evaluation.

### Langfuse evaluation

Use Langfuse prompt versions plus datasets/experiments to compare:

- `generate`
- `generate_exhaustive_list`

Do this before promoting the new prompt version to production labels.

### Retrieval validation

Measure:

- unique source document count
- top-N dominance by a single document
- coverage of expected answer variants on the golden set

### Regression guardrails

Verify that ordinary short knowledge questions remain concise and do not drift into list-heavy answers.

## Risks

### False positive coverage detection

If the heuristic is too broad, too many questions will trigger longer answers.

Mitigation:

- start with high-precision phrases
- log trigger reason in observability

### Weak or inconsistent document identifier

Grouping depends on a stable payload field.

Mitigation:

- inspect payloads first
- fall back to local per-document cap logic if needed

### Over-grouping

Aggressive grouping may hide useful adjacent chunks from the same document.

Mitigation:

- start with `group_size=2`
- validate on golden coverage questions

### Prompt over-expansion

Coverage prompt may become too verbose for Telegram.

Mitigation:

- require grouped, deduplicated output
- keep answer structure disciplined even while allowing more items

## Decision Log

- Chosen approach: two short rollouts, generation first, retrieval second
- Rejected for now: full retrieval redesign with immediate MMR integration
- Rejected for now: global bot-wide intent contract
- Rejected for now: LLM-based coverage detection

## Shipping Order

### PR1

- `needs_coverage`
- `generate_exhaustive_list`
- coverage-mode priority over style routing
- observability
- Langfuse experiment on golden set

### PR2

- grouping-based coverage retrieval
- per-document cap fallback if needed
- retrieval observability
- reevaluate golden set

### Possible PR3 only if needed

- MMR for residual redundancy after grouping

## Open Questions

- What payload field should be treated as the canonical document identifier in the current Qdrant collection?
- Should the detector be limited to Russian initially, or include English/Ukrainian trigger phrases from the start?
- Should coverage mode enforce source display automatically when a list is generated, or remain independent from `show_sources`?
