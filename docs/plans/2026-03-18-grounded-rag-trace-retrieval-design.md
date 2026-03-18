# Grounded RAG Trace And Retrieval Design

Date: 2026-03-18
Branch: `dev`
Scope: `telegram_bot/`, retrieval runtime, Langfuse tracing, Qdrant retrieval policy, knowledge schema, legal/relocation corpus quality

## Purpose

This design defines the target architecture for the bot's grounded RAG path so the system becomes correct by construction across four layers:

- runtime orchestration
- observability and evaluation
- retrieval policy
- knowledge layer quality

The immediate trigger is the recent investigation into slow and noisy traces for legal and relocation-style queries such as `виды внж в болгарии?`. The latest fixes reduced latency materially, but they also exposed the deeper issue: the system is no longer primarily failing due to retrieval mechanics. It is now limited by inconsistent observability contracts, policy ambiguity around constrained versus relaxed retrieval, and weak coverage or tagging in the legal knowledge layer.

The target state is not "make a slow trace faster". The target state is:

- one explainable trace per user request
- a single downstream state contract after `pre_agent`
- explicit retrieval policy and explicit relax behavior
- strict grounded handling for `legal / ВНЖ / relocation`
- safe fallback when grounding requirements are not met
- corpus and payload schema that support the runtime policy rather than fight it

## Design Goals

Primary goals:

- Make every trace readable top-down at the business level.
- Remove duplicated or implicit runtime decisions after `pre_agent`.
- Treat `topic-relax` as a first-class retrieval policy, not as accidental repeated search.
- Enforce `strict grounded mode` for high-risk legal and relocation questions.
- Expand the scope beyond runtime into metadata schema, chunking, and corpus coverage.

Non-goals:

- Replacing Qdrant with a different retrieval engine.
- Removing semantic cache.
- Reverting to agent-first orchestration for normal RAG queries.
- Solving all answer quality issues purely by prompt engineering.

## Architectural Principles

1. `Pre-agent` remains a visible business stage in Langfuse.
2. `Pre-agent` must not remain a separate technical world.
3. Every miss path must carry a complete state contract into retrieval.
4. High-risk answers must be grounded or explicitly degraded.
5. Retrieval policy must be observable and testable.
6. Knowledge quality is part of system architecture, not external data debt.

## Target Runtime Shape

The target runtime path for a normal request is:

- `request`
- `pre_agent`
- `pre_agent_cache_hit` or `pre_agent_miss`
- `retrieval.initial`
- `retrieval.relax` when policy requires it
- `generation`
- `grounding`
- `postprocess`
- `safe_fallback` when strict grounding cannot be satisfied

`Pre-agent` remains responsible for:

- exact cache check
- semantic cache check
- query classification
- query embedding bundle creation when the request is cacheable

If there is a semantic hit, the request exits through `pre_agent_cache_hit`.

If there is a miss, `pre-agent` must emit a complete state contract that downstream code consumes without repeating semantic cache logic or re-deriving known facts.

## State Contract

After `pre_agent_miss`, downstream code must receive a single contract object with fields equivalent to:

- `cache_checked: true`
- `cache_hit: false`
- `cache_scope: rag`
- `embedding_bundle_ready: true|false`
- `embedding_bundle_version: bge_m3_hybrid_colbert`
- `dense_vector`
- `sparse_vector`
- `colbert_query`
- `query_type`
- `topic_hint`
- `retrieval_policy`
- `grounding_mode`
- `knowledge_scope`

Required policy values:

- `retrieval_policy: topic_then_relax`
- `grounding_mode: strict` for `legal / ВНЖ / relocation`
- `grounding_mode: normal` for lower-risk classes

Rules:

- `retrieval` must not repeat semantic cache checks when `cache_checked=true`.
- `retrieval` must not issue a second embedding pass if `embedding_bundle_ready=true`.
- `generation` must know whether the request is in strict grounded mode before prompt assembly.

## Trace Contract

The Langfuse trace must model business stages first and SDK details second.

Top-level trace name:

- `telegram-message` or another user-action name, not provider endpoint names

First-level spans:

- `pre_agent`
- `retrieval`
- `generation`
- `grounding`
- `postprocess`

Child spans under `pre_agent`:

- `exact_cache_check`
- `semantic_cache_check`
- `query_embed`
- `pre_agent_cache_hit` or `pre_agent_miss`

Child spans under `retrieval`:

- `retrieval.initial`
- `retrieval.relax` when triggered
- low-level child spans such as `bge-m3-hybrid-colbert-embed` and `qdrant-hybrid-search-rrf-colbert`

Trace-level metadata:

- `route`
- `pipeline_mode`
- `query_type`
- `topic_hint`
- `grounding_mode`
- `collection`
- `environment`
- `knowledge_scope`

Observation-level metadata:

- `cache_hit`
- `cache_stage`
- `embedding_bundle_ready`
- `embedding_bundle_version`
- `initial_filters`
- `final_filters`
- `initial_results_count`
- `results_count`
- `retrieval_relaxed`
- `retrieval_relax_reason`
- `qdrant_search_attempts`
- `colbert_used`

Tags should be used for durable filtering slices, for example:

- `client_direct`
- `semantic-cache`
- `strict-grounded`
- `topic-relax`
- `qdrant`
- `colbert`

Scores should be reserved for judgments and evaluation signals:

- `grounded`
- `sources_shown`
- `retrieval_coverage`
- `legal_answer_safe`
- `semantic_cache_safe_reuse`
- `answer_complete`

## Retrieval Policy

The primary retrieval policy for legal and relocation queries is:

- initial constrained retrieval using topic-aware filters
- explicit relax stage when constrained retrieval is insufficient
- grounded generation only if retrieved evidence quality is adequate

Current observed policy:

- `topic=legal` can over-constrain retrieval
- relax often expands results materially
- some top unfiltered documents appear relevant but lack payload classification

Target policy changes:

1. Keep the constrained stage.
2. Make relax a first-class retrieval stage.
3. Make relax threshold explicit and configurable.
4. Track constrained and relaxed outcomes separately in trace metadata and scores.
5. Consider moving from hard `topic` filter to soft preference for some legal classes if corpus tagging remains incomplete.

The second retrieval call is acceptable when policy requires it. It is not acceptable for that second call to be opaque.

## Strict Grounded Mode

`Strict grounded mode` applies to:

- `legal`
- `ВНЖ / immigration`
- `relocation`

Behavioral rules:

- Do not emit a fully confident answer without adequate retrieved evidence.
- Do not treat source-free generation as success.
- Do not reuse semantic cache blindly for these classes unless the cached response was originally grounded and marked safe for reuse.

Strict grounded mode success criteria:

- sufficient retrieved context
- explicit source availability
- no internal signal that coverage is weak or conflicting

If criteria are not met, the system must produce `safe_fallback`.

## Safe Fallback

`Safe fallback` is a valid answer mode, not an error.

Required behavior:

- state that the system cannot confidently provide a complete answer from current materials
- show the best available sources
- describe the failure mode in compact language:
  - weak coverage
  - too few relevant legal documents
  - inconsistent evidence
  - outdated materials

Optional next step:

- manual review or escalation path

## Knowledge Layer Redesign

The runtime policy cannot be considered correct unless the knowledge layer supports it.

### Target Payload Schema

At minimum:

- `topic`
- `doc_type`
- `jurisdiction`
- `audience`
- `freshness`
- `source_type`
- `language`

Recommended additions for legal and relocation content:

- `domain_subtopic` such as `immigration`, `residency`, `tax`, `purchase_process`
- `grounding_tier` such as `primary`, `secondary`, `marketing`
- `effective_date`
- `reviewed_at`

### Tagging Principles

- `topic=legal` is too coarse for immigration-heavy flows.
- Add subtopic coverage for `immigration` or `residency`.
- Prefer multi-attribute payload over one overloaded topic label.

### Chunking Principles

Legal and relocation documents should be chunked around meaning-bearing units:

- eligibility basis
- requirements
- process steps
- timelines
- exceptions
- document lists

Avoid chunks that merge unrelated legal concepts into broad narrative blocks.

### Corpus Audit

Build an audit set around real user intents:

- `виды внж в болгарии`
- `основания для внж в болгарии`
- `типы вида на жительство в болгарии`
- English paraphrases for the same intent

For each query, review:

- constrained top-k
- relaxed top-k
- payload coverage
- source freshness
- chunk quality

## Evaluation Plan

Use production traces to build targeted datasets in Langfuse.

Initial datasets:

- `retrieval/legal`
- `retrieval/relocation`
- `cache/semantic-hit`
- `cache/semantic-miss`
- `policy/topic-relax`

Track at least:

- latency
- groundedness
- sources visibility
- retrieval coverage
- legal answer safety
- safe fallback rate

This creates a closed loop:

- online traces expose failures
- failures become dataset items
- experiments validate policy, prompt, and corpus changes

## Rollout Plan

Phase 1: Observability and contracts

- finalize trace contract
- finalize state contract
- ensure `pre_agent_miss` passes complete retrieval state
- add explicit retrieval policy markers everywhere

Phase 2: Strict grounded runtime

- enable strict grounded mode for legal and relocation classes
- implement `safe_fallback`
- gate semantic cache reuse for grounded high-risk answers

Phase 3: Knowledge schema and corpus quality

- extend payload schema
- add or fix payload indexes on restrictive fields
- audit legal and relocation corpus
- retag and rechunk weak materials

Phase 4: Evaluation loop

- build datasets from live traces
- define stable score rubric
- compare policy changes in Langfuse experiments

## Validation

Runtime validation:

- targeted unit tests for state contract propagation
- targeted integration tests for `pre_agent -> retrieval -> safe_fallback`
- graph path tests where applicable

Retrieval validation:

- constrained vs relaxed result-count assertions
- legal query regression set
- payload coverage checks

Knowledge validation:

- corpus audit report for legal and relocation topics
- chunking spot checks
- payload completeness checks

Observability validation:

- trace contract assertions on required metadata and spans
- score coverage tests for strict grounded mode

## Acceptance Criteria

This design is complete when:

- every legal or relocation trace is readable top-down without manual reconstruction
- `pre_agent` remains visible but no longer duplicates downstream logic
- constrained versus relaxed retrieval is explicit in trace and scores
- strict grounded mode and safe fallback are live
- knowledge schema supports legal and relocation retrieval with measurable coverage
- Langfuse datasets and experiments exist for the main failure classes

## Execution Notes

Implemented on issue branch `wt/issue-1002-grounded-rag` on 2026-03-18.

Final trace contract shipped:

- root metadata now propagates `route`, `pipeline_mode`, `query_type`, `topic_hint`, `grounding_mode`, `collection`, and `environment`
- `pre_agent` miss now emits a typed downstream `state_contract`
- retrieval spans now expose `retrieval.initial` and `retrieval.relax`
- retrieval metadata now records `initial_filters`, `final_filters`, `qdrant_search_attempts`, and `retrieval_relaxed_from_topic_filter`

Final score additions shipped:

- `grounded`
- `legal_answer_safe`
- `semantic_cache_safe_reuse`
- `safe_fallback_used`

Final payload schema additions shipped:

- `metadata.jurisdiction`
- `metadata.language`
- `metadata.source_type`
- `metadata.audience`

Validation status:

- targeted unit suites passed for pipeline, retrieval, generation, ingestion, observability, and score coverage
- repo-wide `make check` and `make test-unit` were added as rollout gates in execution
- legal grounding audit harness currently runs in `offline_fixture_only` mode and confirms strict-topic classification plus safe fallback behavior for the sample fixture set
- live-stack corpus validation traces were not captured in this execution note, so corpus sufficiency in production still requires a follow-up trace capture against the running stack
