W-SDK-RESEARCH: Best practices 2026 — Qdrant SDK, Redis SDK, BGE-M3 ONNX, ONNX Runtime

Работай из /repo.

КОНТЕКСТ:
RAG pipeline на Python 3.12. Стек: Qdrant (vector DB), Redis (cache), BGE-M3 (embeddings), ONNX Runtime (target inference).
Нужно собрать актуальные SDK best practices на 2026 год для каждого компонента.

ЗАДАЧИ:

1. QDRANT SDK (qdrant-client) — через Exa и Context7:
   - Актуальная версия qdrant-client в 2026, breaking changes
   - AsyncQdrantClient best practices (connection pooling, timeouts, retries)
   - query_points vs search (новый API)
   - Prefetch + RRF (Reciprocal Rank Fusion) через SDK
   - Sparse vectors (named vectors) configuration
   - Quantization: scalar vs binary vs product, когда какой
   - Payload indexes — когда создавать, impact на latency
   - Batch operations (upsert, search batch)
   - gRPC vs REST — benchmark, когда что
   - Sharding и replication для production
   - Collection optimizer settings (memmap, indexing threshold)
   Используй: get_code_context_exa("qdrant-client python 2026 best practices async query_points")
   Используй: get_code_context_exa("qdrant sparse vectors named vectors RRF prefetch")
   Используй: Context7 resolve-library-id("qdrant-client") -> query-docs

2. REDIS SDK (redis-py + redis-vl-python) — через Exa и Context7:
   - redis-py async best practices 2026 (connection pooling, pipelines)
   - redis-vl-python (RedisVL) — SemanticCache API
   - Eviction policies для RAG cache (volatile-lfu vs allkeys-lru)
   - Memory optimization (maxmemory, compression)
   - Redis Stack vs Redis OSS — что нужно для vector search
   - Pipeline batching для cache operations
   - TTL strategies для embedding cache vs search cache vs semantic cache
   - Redis Cluster vs Sentinel для HA
   - Monitoring: INFO stats, keyspace_hits/misses, slowlog
   Используй: get_code_context_exa("redis-vl-python semantic cache 2026")
   Используй: get_code_context_exa("redis python async pipeline best practices 2026")
   Используй: Context7 resolve-library-id("redis-vl-python") -> query-docs

3. BGE-M3 + ONNX Runtime — через Exa:
   - ONNX Runtime best practices 2026 для embedding models
   - onnxruntime ExecutionProvider: CPU vs CUDA vs TensorRT
   - Session options: intra_op_num_threads, inter_op_num_threads, graph_optimization_level
   - INT8 quantization для BGE-M3: optimum export pipeline
   - gpahal/bge-m3-onnx-int8 — как использовать, API
   - Sparse vector extraction из ONNX output (BGE-M3 specific)
   - ColBERT output extraction из ONNX (для reranking)
   - Dynamic quantization vs static quantization
   - Memory mapping для больших моделей
   - Warmup и model compilation
   - Comparison: optimum vs onnxruntime directly vs sentence-transformers ONNX backend
   Используй: get_code_context_exa("BGE-M3 ONNX runtime INT8 quantization embedding 2026")
   Используй: get_code_context_exa("optimum ORTModelForCustomTasks sentence-transformers ONNX export")
   Используй: web_search_exa("BGE-M3 ONNX INT8 production deployment 2026 benchmark")

4. PRODUCTION PATTERNS (cross-cutting) — через Exa:
   - Embedding server architecture patterns 2026
   - Health checks и graceful degradation для ML services
   - Batching strategies (dynamic batching, request coalescing)
   - Caching layers: L1 (in-process) vs L2 (Redis) vs L3 (disk)
   - Observability: OpenTelemetry для inference services
   - Rate limiting и backpressure для embedding APIs
   Используй: web_search_exa("embedding server production architecture 2026 best practices")

5. ДЛЯ КАЖДОГО SDK — сформируй:
   - Текущая версия и changelog highlights
   - Top-5 best practices с примерами кода
   - Антипаттерны (что НЕ делать)
   - Таблица: наш текущий код vs recommended

ВЫВОД: Полный отчёт с таблицами, code snippets, рекомендациями.

НЕ МЕНЯЙ КОД. Только исследование и отчёт.

ЛОГИРОВАНИЕ в /repo/logs/worker-sdk-research.log (APPEND):
echo "[TAG] $(date +%H:%M:%S) message" >> /repo/logs/worker-sdk-research.log
Пиши ВСЕ результаты ПРЯМО в лог (полные таблицы, code snippets, findings).
Теги: [START], [QDRANT], [REDIS], [ONNX], [PATTERNS], [RECOMMENDATION], [COMPLETE]

После завершения выполни:
1. TMUX="" tmux send-keys -t "claude:1" "W-SDK-RESEARCH COMPLETE — проверь logs/worker-sdk-research.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:1" Enter
