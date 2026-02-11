W-BGE-RESEARCH: Исследование best practices 2026 для ускорения BGE-M3 embeddings

Работай из /repo.

КОНТЕКСТ ПРОБЛЕМЫ:
Трейс 2b920c515cdd5315a2575ae0b8059bbb показал:
- bge-m3-dense-embed: 6,278ms (58% total latency)
- bge-m3-sparse-embed: 7,847ms (72% total latency)
- Два раздельных вызова (dense отдельно, sparse отдельно) вместо одного /encode/hybrid
- BGE-M3 на CPU (PyTorch), без ONNX
- Qdrant search всего 172ms — bottleneck целиком в embedding
- Total latency: 10.8 секунд на один RAG запрос

ТЕКУЩАЯ АРХИТЕКТУРА:
- BGE-M3 сервер: services/bge-m3-api/ (FastAPI, PyTorch, CPU)
- Endpoints: /encode/dense, /encode/sparse, /encode/hybrid, /rerank
- Docker контейнер: rag-fresh-bge-m3, ~2.3GB
- Клиент: telegram_bot/integrations/embeddings.py
- Вызовы: последовательные dense + sparse в разных graph nodes

ЗАДАЧИ:

1. Через Exa MCP найди актуальные (2026) решения для:
   - ONNX Runtime для BGE-M3 (sentence-transformers export, optimum)
   - Batched inference для BGE-M3
   - GPU vs CPU оптимизация для embedding серверов
   - Infinity embedding server, TEI (Text Embeddings Inference by HuggingFace), vLLM embeddings
   - Quantization (INT8/FP16) для BGE-M3 на CPU
   - Connection pooling и async для embedding API

   Используй: mcp exa get_code_context_exa и web_search_exa

2. Через Exa найди бенчмарки:
   - BGE-M3 ONNX vs PyTorch throughput
   - BGE-M3 на TEI vs custom FastAPI
   - BGE-M3 INT8 quantization quality impact
   - Latency comparison: dense-only vs hybrid (tri-vector)

3. Через Exa найди production deployments BGE-M3:
   - Как крупные проекты деплоят BGE-M3 в 2026
   - Рекомендации по max_length, batch_size, concurrency
   - OMP_NUM_THREADS / MKL_NUM_THREADS best practices

4. Сформируй итоговый отчёт в лог с таблицей решений:
   | Решение | Ожидаемый выигрыш | Сложность | Риски |
   Ранжируй по impact/effort ratio.

5. Прочитай текущий BGE-M3 сервер (services/bge-m3-api/) и клиент (telegram_bot/integrations/embeddings.py) чтобы дать конкретные рекомендации для НАШЕГО кода.

НЕ МЕНЯЙ КОД. Только исследование и отчёт.

ЛОГИРОВАНИЕ в /repo/logs/worker-bge-research.log (APPEND):
echo "[TAG] $(date +%H:%M:%S) message" >> /repo/logs/worker-bge-research.log
Пиши результаты исследования ПРЯМО в лог (не только теги, а полный отчёт с таблицами).
Теги: [START], [FINDING], [BENCHMARK], [RECOMMENDATION], [COMPLETE]

После завершения выполни:
1. TMUX="" tmux send-keys -t "claude:1" "W-BGE-RESEARCH COMPLETE — проверь logs/worker-bge-research.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:1" Enter
