W-FIX-C: Починить 9 тестов в test_search_engines.py + test_acorn.py

Работай из /home/user/projects/rag-fresh

Проблемы:
- Qdrant client API change: client.search() удалён, нужен query_points()
- test_acorn: engine.client = None, нужен mock_qdrant_client
- Тесты используют реальный QdrantClient который лезет в Docker

Шаги:

1. Прочитай tests/unit/test_search_engines.py — найди вызовы client.search()
2. Прочитай src/retrieval/search_engines.py — пойми текущий API (query_points vs search)
3. Замени mock expectations с .search() на .query_points() где нужно
4. Mock QdrantClient полностью через MagicMock чтобы не лезть в Docker
5. Прочитай tests/unit/test_acorn.py — установи engine.client = mock_qdrant_client
6. Запусти: uv run pytest tests/unit/test_search_engines.py tests/unit/test_acorn.py -v --tb=short
7. Фикси пока все зелёные

После успеха:
- git add tests/unit/test_search_engines.py tests/unit/test_acorn.py
- git commit -m "fix(tests): update search engine tests for Qdrant query_points API

9 tests fixed: migrate from removed client.search() to query_points(),
mock QdrantClient to prevent Docker hits.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

Логирование в /home/user/projects/rag-fresh/logs/worker-fix-c.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-FIX-C COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
