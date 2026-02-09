Напиши unit тесты для src/ingestion/unified/flow.py

GitHub Issue: #51 — test: cover critical unified ingestion modules
Работай из /repo

SKILLS (обязательно вызови):
1. /test-driven-development — RED → GREEN → REFACTOR
2. /verification-before-completion — проверка после написания

## Шаги

1. Прочитай src/ingestion/unified/flow.py — пойми что делает (CocoIndex orchestration)
2. Прочитай существующие тесты в tests/unit/ingestion/ — пойми паттерны
3. Создай tests/unit/ingestion/test_unified_flow.py
4. Покрой:
   - Flow setup / initialization
   - Document processing pipeline
   - Error handling paths
   - Мокай внешние зависимости (CocoIndex, Qdrant)
5. Запусти: uv run pytest tests/unit/ingestion/test_unified_flow.py -v
6. Убедись все зелёные

## Правила
- git add tests/unit/ingestion/test_unified_flow.py
- git commit -m "test(ingestion): add unit tests for unified flow module

Closes #51 (partial)

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
- Тесты ТОЛЬКО свои: tests/unit/ingestion/test_unified_flow.py

## Логирование
/repo/logs/worker-test-flow.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

## Webhook
После завершения:
TMUX="" tmux send-keys -t "claude:1" "W-FLOW COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
