W-TRACE-AUDIT: Глубокий аудит Langfuse трейсов — покрытие spans, scores, кешей

Работай из /home/user/projects/rag-fresh.

КОНТЕКСТ:
Бот поднят, трейсы пишутся в Langfuse (http://localhost:3001).
Credentials: см. .env файл (LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_HOST)
API: curl -s -u "$PUBLIC_KEY:$SECRET_KEY" "$HOST/api/public/..."

ЗАДАЧИ:

1. СОБЕРИ ВСЕ ТРЕЙСЫ за последние сутки:
   curl -u ... "$HOST/api/public/traces?limit=50" | выведи список (id, name, timestamp, latency)

2. ДЛЯ КАЖДОГО УНИКАЛЬНОГО ТИПА ТРЕЙСА (FAQ, GENERAL, GREETING, cache_hit, no_results) возьми по одному и разбери observations:
   curl -u ... "$HOST/api/public/observations?traceId=XXX&limit=100"
   Построй дерево spans с duration для каждого.

3. АУДИТ ПОКРЫТИЯ SPANS — проверь что каждый node графа имеет span:
   Ожидаемые nodes (из telegram_bot/graph/):
   - node-classify
   - node-cache-check
   - node-retrieve
   - node-grade
   - node-rewrite (если был rewrite)
   - node-generate
   - node-cache-store
   - node-respond
   Есть ли пропущенные? Есть ли лишние?

4. АУДИТ ПОКРЫТИЯ SCORES — проверь что все scores пишутся:
   Ожидаемые (из telegram_bot/bot.py _write_langfuse_scores):
   - latency_total_ms
   - semantic_cache_hit
   - embeddings_cache_hit
   - search_cache_hit
   - rerank_cache_hit
   - rerank_applied
   - results_count
   - no_results
   - hyde_used
   - llm_used
   - query_type
   - confidence_score
   Какие есть? Какие отсутствуют? Какие всегда 0?

5. АУДИТ КЕШЕЙ — для каждого типа кеша проверь по трейсам:
   a) Semantic cache (RedisVL): cache-semantic-check span, semantic_cache_hit score
   b) Embedding cache: cache-embedding-get/store spans, embeddings_cache_hit score
   c) Search cache: cache-exact-get/store spans, search_cache_hit score
   d) Rerank cache: rerank_cache_hit score
   - Работают ли кеши? (повторный запрос должен дать hit)
   - Какие latency у cache operations?
   - Есть ли cache misses которые должны быть hits?

6. АУДИТ LATENCY BREAKDOWN — построй таблицу средних latency по spans:
   | Span | Min ms | Avg ms | Max ms | % of total |
   Найди аномалии и bottlenecks.

7. АУДИТ METADATA — проверь что trace metadata полная:
   - input (query)
   - output (response)
   - query_type
   - cache_hit
   - search_results_count
   - rerank_applied
   - user_id / session_id

8. ПРОВЕРЬ EDGE CASES:
   - Что происходит при rewrite loop? (node-rewrite → node-retrieve → node-grade цикл)
   - Что при streaming fallback? (response_sent в metadata)
   - Что при пустых результатах? (no_results score)

ВЫВОД: Сформируй полный отчёт с таблицами и рекомендациями.

НЕ МЕНЯЙ КОД. Только анализ и отчёт.

Также прочитай код observability:
- telegram_bot/observability.py
- telegram_bot/bot.py (функция _write_langfuse_scores)
- telegram_bot/graph/nodes/ (все nodes — как пишут spans)
- telegram_bot/integrations/cache.py (как кеши логируют)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-trace-audit.log (APPEND):
echo "[TAG] $(date +%H:%M:%S) message" >> /home/user/projects/rag-fresh/logs/worker-trace-audit.log
Пиши ВСЕ результаты аудита ПРЯМО в лог (полные таблицы, findings, рекомендации).
Теги: [START], [TRACES], [SPANS], [SCORES], [CACHE], [LATENCY], [FINDING], [RECOMMENDATION], [COMPLETE]

После завершения выполни:
1. TMUX="" tmux send-keys -t "claude:1" "W-TRACE-AUDIT COMPLETE — проверь logs/worker-trace-audit.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:1" Enter
