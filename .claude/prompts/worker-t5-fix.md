W-FIX: Fix validate_traces.py bugs + re-run validation

Работай из /repo.

SKILLS (обязательно вызови):
1. /systematic-debugging — для анализа бага
2. /verification-before-completion — после фикса

БАГИ ДЛЯ ФИКСА:

БАГ 1 (CRITICAL): TypeError на line 268 scripts/validate_traces.py
Ошибка: _run() got an unexpected keyword argument 'langfuse_observation_id'
Причина: @observe() decorator НЕ принимает langfuse_observation_id как kwarg.
Действия:
- Используй Context7: resolve-library-id(libraryName="langfuse", query="set trace id observe decorator") затем query-docs для проверки ПРАВИЛЬНОГО API
- Проверь telegram_bot/observability.py и telegram_bot/bot.py:229-281 — как проект уже использует @observe
- Исправь run_single_query() чтобы trace_id передавался корректно через Langfuse SDK v3

БАГ 2: legal_documents коллекция не найдена в Qdrant
Доступные коллекции: gdrive_documents_bge, contextual_bulgaria_voyage, gdrive_documents_binary, gdrive_documents_scalar
Действия:
- В COLLECTIONS_TO_CHECK заменить "legal_documents" на "gdrive_documents_bge"
- gdrive_documents_bge использует BGE-M3 embeddings — совместим с langgraph_bge runner mode
- detect_runner_mode("gdrive_documents_bge") должен возвращать "langgraph_bge"

БАГ 3: LANGFUSE_SECRET_KEY не найден
Проверь .env файл — есть ли LANGFUSE_SECRET_KEY. Если есть — проблема в том что скрипт не загружает .env.
Действия:
- Добавь load_dotenv() в начало main() или в check_langfuse_config()
- from dotenv import load_dotenv

ПОСЛЕ ФИКСОВ:

1. Запусти тесты: uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v
2. Lint: uv run ruff check scripts/validate_traces.py scripts/validate_queries.py
3. git commit конкретные файлы (Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>)
4. Запусти валидацию: uv run python scripts/validate_traces.py --collection gdrive_documents_bge --report
5. Покажи итоговый отчёт: cat docs/reports/*.md (последний файл)

MCP TOOLS:
- Context7: resolve-library-id(libraryName="langfuse", query="observe decorator trace id python SDK v3") затем query-docs для правильного API
- Exa: get_code_context_exa(query="langfuse python observe decorator set trace id") для примеров

ТЕСТЫ:
- scripts/validate_queries.py -> tests/unit/test_validate_queries.py
- scripts/validate_traces.py -> tests/unit/test_validate_aggregates.py
- Запускай ТОЛЬКО эти два файла

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
3. НЕ останавливайся — фикс, тесты, прогон, отчёт — всё подряд.

ЛОГИРОВАНИЕ в /repo/logs/worker-fix-run.log (APPEND):
echo "[START] $(date +%H:%M:%S) description" >> /repo/logs/worker-fix-run.log
echo "[DONE] $(date +%H:%M:%S) result" >> /repo/logs/worker-fix-run.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-fix-run.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-FIX COMPLETE — проверь logs/worker-fix-run.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
