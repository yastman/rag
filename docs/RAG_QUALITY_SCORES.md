# RAG Quality Scores

Observability metrics written to Langfuse for every query.

## Score Writing

Scores are computed and written via `src/scoring.py` (re-exported through the
`telegram_bot/scoring.py` shim for historical bot imports):
- `write_langfuse_scores()` — main query scores
- `write_history_scores()` — history search scores
- `write_crm_scores()` — CRM tool usage scores

> **Drift guard:** the doc/code parity is enforced by
> [`tests/contract/test_rag_quality_scores_doc_drift.py`](../tests/contract/test_rag_quality_scores_doc_drift.py).
> Whenever a new `name=...` is added to `scoring.py`, add a row below or
> entry in `DOC_EXEMPT_SCORE_NAMES`.

## When are scores written

Quality scores and per-node observability use **two different** Langfuse
mechanisms with different timing:

- **Quality scores are written once per query, at the end of the pipeline**, by
  `write_langfuse_scores()` (`src/scoring.py`). It reads the final graph
  `result` state and emits every score in one pass via the `score(...)` helper,
  which calls `lf.create_score(trace_id=..., score_id="<trace_id>-<name>")` —
  explicit trace scoping plus an idempotency key (#435). The bot calls it after
  the supervisor run completes (`telegram_bot/bot.py`); the RAG API calls it at
  the end of `/query` (`src/api/main.py`). `write_history_scores()` and
  `write_crm_scores()` follow the same once-per-flow pattern.
- **Per-node hit/miss and grade signals are NOT scores.** Nodes such as the
  cache node (`telegram_bot/graph/nodes/cache.py`) report real-time state with
  `lf.update_current_span(input=..., output=..., metadata=...)`, not
  `score_current_trace` / `create_score`. That is why you will not find a
  `score_current_trace` call inside `cache_check_node`: the cache hit/miss is
  surfaced on the span in real time and the corresponding `semantic_cache_hit` /
  `embeddings_cache_hit` / `search_cache_hit` *scores* are written later, in the
  single end-of-query `write_langfuse_scores()` pass.

In short: span `input`/`output`/`metadata` is the live, per-node channel;
Langfuse **scores** are the end-of-query summary. Entry point and ordering:
`write_langfuse_scores(lf, result, trace_id=...)` in `src/scoring.py`.

## Main Query Scores

| Score | Type | Description |
|-------|------|-------------|
| `query_type` | numeric | Query type weight: CHITCHAT=0, OFF_TOPIC=0, others=1-2 |
| `latency_total_ms` | numeric | End-to-end latency |
| `semantic_cache_hit` | boolean | Semantic result cache hit |
| `embeddings_cache_hit` | boolean | Embeddings cache hit |
| `search_cache_hit` | boolean | Search cache hit |
| `rerank_applied` | boolean | ColBERT reranking was applied |
| `rerank_cache_hit` | boolean | Rerank results served from cache |
| `results_count` | numeric | Number of search results |
| `no_results` | boolean | No results returned |
| `llm_used` | boolean | LLM generation was called |
| `confidence_score` | numeric | Grade confidence (RRF scale) |
| `llm_ttft_ms` | numeric | Time to first token |
| `llm_response_duration_ms` | numeric | LLM generation duration |
| `streaming_enabled` | boolean | Streaming was enabled |
| `llm_timeout` | boolean | LLM timeout occurred |
| `llm_stream_recovery` | boolean | Stream recovery was triggered |
| `llm_decode_ms` | numeric | LLM decode time (if available) |
| `llm_decode_unavailable` | boolean | Decode time not available |
| `llm_tps` | numeric | Tokens per second (if available) |
| `llm_tps_unavailable` | boolean | TPS not available |
| `llm_queue_ms` | numeric | Queue time (if available) |
| `llm_queue_unavailable` | boolean | Queue time not available |
| `answer_words` | numeric | Word count of generated answer |
| `answer_chars` | numeric | Character count of answer |
| `answer_to_question_ratio` | numeric | Answer length vs question length |
| `response_style_applied` | numeric | Style: short=0, balanced=1, detailed=2 |
| `input_type` | categorical | `text` or `voice` |
| `stt_duration_ms` | numeric | Speech-to-text duration (voice only) |
| `voice_duration_s` | numeric | Voice input duration (voice only) |
| `bge_embed_error` | boolean | Embedding service error occurred |
| `bge_embed_latency_ms` | numeric | Embedding latency |
| `bge_model_processing_ms` | numeric | Pure model-side BGE-M3 processing time (separates network/queue from inference) |
| `security_alert` | boolean | Prompt injection detected |
| `injection_risk_score` | numeric | Injection risk score (0-1) |
| `injection_pattern` | categorical | Type of injection pattern detected |
| `llm_calls_total` | numeric | Total LLM calls in query |
| `summarize_ms` | numeric | Summarization node latency |
| `memory_messages_count` | numeric | Messages in conversation memory |
| `summarization_triggered` | boolean | Conversation was summarized |
| `grounded` | boolean | Answer grounded in retrieved context |
| `legal_answer_safe` | boolean | No legal disclaimers needed |
| `semantic_cache_safe_reuse` | boolean | Cache reuse was safe |
| `safe_fallback_used` | boolean | Safe fallback response used |
| `checkpointer_overhead_proxy_ms` | numeric | Checkpoint overhead proxy |
| `checkpointer_overhead_ms` | numeric | Direct checkpointer Redis I/O time, summed from `InstrumentedCheckpointer` (#1258); excludes Pregel framework overhead unlike the proxy |
| `checkpointer_op_count` | numeric | Number of timed checkpointer operations (`aput`/`aget`/`aput_writes`/`aget_tuple`) per query (#1258) |
| `nurturing_batch_size` | numeric | Nurturing batch size |
| `nurturing_sent_count` | numeric | Nurturing messages sent |
| `funnel_conversion_rate` | numeric | Funnel conversion rate |
| `funnel_dropoff_rate` | numeric | Funnel drop-off rate |
| `sources_shown` | boolean | Sources were shown in response |
| `sources_count` | numeric | Number of sources shown |

## History Search Scores

Written via `write_history_scores()` for `/history` searches:

| Score | Type | Description |
|-------|------|-------------|
| `history_search_count` | numeric | Number of history results |
| `history_search_latency_ms` | numeric | History search latency |
| `history_search_empty` | numeric | 1 if no results, 0 otherwise |
| `history_backend` | categorical | Search backend used |

## CRM Scores

Written via `write_crm_scores()` when CRM tools are invoked:

| Score | Type | Description |
|-------|------|-------------|
| `crm_tool_used` | boolean | Any CRM tool was called |
| `crm_tools_count` | numeric | Total CRM tool calls |
| `crm_tools_success` | numeric | Successful CRM operations |
| `crm_tools_error` | numeric | Failed CRM operations |

## Query Type Weights

| Query Type | Weight | Notes |
|------------|--------|-------|
| `CHITCHAT` | 0.0 | No RAG needed |
| `OFF_TOPIC` | 0.0 | No RAG needed |
| `SIMPLE` | 1.0 | Simple query |
| `GENERAL` | 1.0 | General knowledge |
| `FAQ` | 1.0 | FAQ query |
| `ENTITY` | 1.0 | Entity lookup |
| `STRUCTURED` | 2.0 | Structured extraction |
| `COMPLEX` | 2.0 | Complex query |

## Validation

Required trace families validated by `make validate-traces-fast`:
- `rag-api-query`
- `voice-session`
- `ingestion-cli-run`

## Code Locations

| File | Purpose |
|------|---------|
| `src/scoring.py` | Canonical score computation and writing (`write_langfuse_scores`, `write_history_scores`, `write_crm_scores`, `score`) |
| `telegram_bot/scoring.py` | Re-export shim for historical bot imports |
| `telegram_bot/observability.py` | Langfuse client setup |
| `docker/monitoring/rules/` | Alert rules |
