W-BGE: Unit тесты для bge-m3-api endpoints (FastAPI TestClient)

GitHub Issue: #52 — test: cover Docker services critical test gaps
Работай из /home/user/projects/rag-fresh

SKILLS (обязательно вызови):
1. /test-driven-development — RED -> GREEN -> REFACTOR
2. /verification-before-completion — проверка после написания

Шаги:

1. Прочитай services/bge-m3-api/app.py — все endpoints и Pydantic модели
2. Прочитай services/bge-m3-api/config.py — Settings класс
3. Прочитай tests/unit/test_bge_m3_rerank.py — паттерн мока FlagEmbedding

4. Создай tests/unit/test_bge_m3_endpoints.py:

   Мокай зависимости:
   - FlagReranker, BGEM3FlagModel из FlagEmbedding
   - prometheus_client (Counter, Histogram)
   Мокай ДО импорта app:
     sys.modules["FlagEmbedding"] = mock_module
     sys.modules["prometheus_client"] = mock_prom

   Тесты (используй httpx.ASGITransport + httpx.AsyncClient с app):

   a) /encode/sparse — POST с texts=["hello"], проверь:
      - status 200
      - response.json() содержит "embeddings" список
      - каждый embedding это dict (lexical_weights формат)

   b) /encode/colbert — POST с texts=["hello"], проверь:
      - status 200
      - response содержит "embeddings" список
      - каждый embedding это list of lists (multi-vector)

   c) /encode/hybrid — POST с texts=["hello"], проверь:
      - status 200
      - response содержит "dense", "sparse", "colbert" ключи

   d) /health — GET, проверь status 200 и "status" в ответе

   e) /metrics — GET, проверь status 200 и text содержит HELP или TYPE

   f) /encode/dense — POST с пустым texts=[], проверь ответ (пустой список или ошибка)

   g) config.py — тест дефолтных значений Settings:
      - MAX_LENGTH=2048, BATCH_SIZE=12, USE_FP16=True
      - RERANK_MAX_DOCS=30, RERANK_MAX_LENGTH=512

5. Запусти: uv run pytest tests/unit/test_bge_m3_endpoints.py -v
6. Фикси пока все не зелёные

Правила:
- git add tests/unit/test_bge_m3_endpoints.py
- git commit -m "test(bge-m3): add FastAPI TestClient tests for all endpoints

Covers /encode/sparse, /encode/colbert, /encode/hybrid, /health, /metrics,
and config defaults. Closes #52 (partial)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
- Тесты ТОЛЬКО свои: tests/unit/test_bge_m3_endpoints.py
- НЕ запускай pytest tests/ целиком

Логирование в /home/user/projects/rag-fresh/logs/worker-bge-tests.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook — после завершения выполни две отдельные bash команды:
Первая: TMUX="" tmux send-keys -t "claude:1" "W-BGE COMPLETE"
Вторая (через пол секунды): sleep 0.5 && TMUX="" tmux send-keys -t "claude:1" Enter
