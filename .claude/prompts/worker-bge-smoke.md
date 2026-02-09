W-BGE-SMOKE: Smoke тест для bge-m3 /encode/dense на live сервисе

Работай из /home/user/projects/rag-fresh
GitHub Issue: #52 — последний item

Docker сервисы уже UP. BGE-M3 на localhost:8000.

Шаги:

1. Проверь что bge-m3 жив: curl -s http://localhost:8000/health
2. Прочитай tests/smoke/test_zoo_smoke.py — паттерн smoke тестов
3. Добавь smoke тест в tests/smoke/test_zoo_smoke.py (или отдельный файл):

   test_bge_m3_encode_dense:
   - POST http://localhost:8000/encode/dense с json={"texts": ["test query"]}
   - Проверь status 200
   - Проверь что response содержит "embeddings" list
   - Проверь len(embeddings[0]) == 1024

   test_bge_m3_encode_sparse:
   - POST http://localhost:8000/encode/sparse с json={"texts": ["test query"]}
   - Проверь status 200

   test_bge_m3_health_detailed:
   - GET http://localhost:8000/health
   - Проверь "model_loaded" в ответе

   Добавь skipIf для случая когда bge-m3 не доступен (socket check на порт 8000)

4. Запусти: uv run pytest tests/smoke/test_zoo_smoke.py -v -k bge_m3 --tb=short
5. Фикси если нужно

После успеха:
- git add тестовый файл
- git commit -m "test(smoke): add live bge-m3 endpoint smoke tests

Covers /encode/dense (1024-dim verify), /encode/sparse, /health.
Skips if bge-m3 not running. Closes #52

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

Логирование в /home/user/projects/rag-fresh/logs/worker-bge-smoke.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-BGE-SMOKE COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
