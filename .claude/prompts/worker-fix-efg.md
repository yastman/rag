W-FIX-EFG: Починить оставшиеся 26 тестов (Groups E+F+G)

Работай из /repo

Group E — test_model_registry.py (6 тестов):
- MLflow mock возвращает MagicMock для .version вместо строки
- transition_model_version_stage не вызывается — API сменился на aliases
- Фикс: обнови моки под текущий MLflow API, set return_value.version = "1"

Group F — test_contextualized_embeddings.py (5 тестов):
- Voyage client mock не возвращает proper embedding arrays
- Mock return values это MagicMock вместо list of floats
- Фикс: set mock return_value к правильным embedding структурам

Group G — misc (15 тестов):
- test_main.py (3): bot.start()/stop() нужен AsyncMock
- test_settings.py (3): API key validation убрана или изменена в Settings — прочитай src/core/settings.py
- test_bot_scores.py (1): query_type scoring logic changed (1.0 vs 2.0) — прочитай код scoring
- test_bge_m3_endpoints.py (2): sparse/colbert endpoints return empty arrays — проверь mock model
- test_cocoindex_flow.py (1): Flow name collision (global state) — добавь unique flow names или cleanup
- test_ingestion_service.py (1): Same CocoIndex flow collision

Шаги:
1. Для каждой группы: прочитай тест файл + source файл
2. Починь моки согласно описанию
3. Запусти тесты по группе после каждого фикса
4. После всех: uv run pytest tests/unit/test_model_registry.py tests/unit/test_contextualized_embeddings.py tests/unit/test_main.py tests/unit/test_settings.py tests/unit/test_bot_scores.py tests/unit/test_bge_m3_endpoints.py tests/unit/test_cocoindex_flow.py tests/unit/test_ingestion_service.py -v --tb=short

После успеха — один коммит:
- git add все затронутые файлы
- git commit -m "fix(tests): repair model registry, embeddings, settings and misc tests

26 tests fixed across 8 files: update MLflow API mocks, fix embedding
return values, AsyncMock for bot startup, align settings validation.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"

Логирование в /repo/logs/worker-fix-efg.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-FIX-EFG COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
