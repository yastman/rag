W-USERBASE: FastAPI TestClient тесты для services/user-base/

GitHub Issue: #52 — test: cover Docker services critical test gaps
Работай из /repo

SKILLS (обязательно вызови):
1. /test-driven-development — RED -> GREEN -> REFACTOR
2. /verification-before-completion — проверка после написания

Шаги:

1. Прочитай services/user-base/main.py — endpoints и модели:
   - GET /health -> HealthResponse (status, model_name, embedding_dim)
   - POST /embed -> EmbedResponse (embedding: list[float])
   - POST /embed_batch -> EmbedBatchResponse (embeddings: list[list[float]])
   - lifespan: загрузка SentenceTransformer при старте

2. Прочитай tests/unit/test_vectorizers.py — паттерн мока

3. Создай tests/unit/test_userbase_endpoints.py:

   Мокай зависимости:
   - sentence_transformers.SentenceTransformer
   - Мокай ПЕРЕД импортом app через sys.modules

   Тесты (используй httpx.ASGITransport + httpx.AsyncClient):

   a) /health — GET:
      - status 200
      - json содержит "status", "model_name", "embedding_dim"
      - embedding_dim == 768

   b) /embed — POST с text="привет":
      - status 200
      - json содержит "embedding" list
      - len(embedding) == 768

   c) /embed_batch — POST с texts=["привет", "мир"]:
      - status 200
      - json содержит "embeddings" list
      - len(embeddings) == 2
      - each len == 768

   d) /embed — POST с пустым text="" :
      - проверь поведение (ошибка или пустой вектор)

   e) /embed_batch — POST с texts=[]:
      - проверь поведение

4. Запусти: uv run pytest tests/unit/test_userbase_endpoints.py -v
5. Фикси пока все не зелёные

Правила:
- git add tests/unit/test_userbase_endpoints.py
- git commit -m "test(user-base): add FastAPI TestClient tests for all endpoints

Covers /health, /embed, /embed_batch with mocked SentenceTransformer.
Closes #52 (partial)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
- Тесты ТОЛЬКО свои: tests/unit/test_userbase_endpoints.py

Логирование в /repo/logs/worker-userbase-tests.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook — после завершения выполни две отдельные bash команды:
Первая: TMUX="" tmux send-keys -t "claude:1" "W-USERBASE COMPLETE"
Вторая (через пол секунды): sleep 0.5 && TMUX="" tmux send-keys -t "claude:1" Enter
