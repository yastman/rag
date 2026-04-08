# RAG Quality Scores

Observability metrics written to Langfuse for every query.

## Score Writing

Scores are computed and written via `telegram_bot/scoring.py`:
- `write_langfuse_scores()` — main query scores
- `write_history_scores()` — history search scores
- `write_crm_scores()` — CRM tool usage scores

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
| `telegram_bot/scoring.py` | Score computation and writing |
| `telegram_bot/observability.py` | Langfuse client setup |
| `docker/monitoring/rules/` | Alert rules |
