W-VERIFY: Final lint + full test suite verification (Task 6 from plan)

SKILLS (обязательно вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения задач
2. /requesting-code-review — code review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion — финальная проверка перед коммитом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-12-memory-observability-plan.md
Работай из /home/user/projects/rag-fresh. Tasks 1-5 уже завершены.

ЗАДАЧА:

Task 6: Lint + targeted tests verification
  1. Code review: просмотри git diff feat/159-memory-observability...HEAD (все 4 коммита), проверь стиль, логику, тесты
  2. Lint: uv run ruff check telegram_bot/bot.py telegram_bot/services/redis_monitor.py tests/unit/test_bot_scores.py tests/unit/services/test_redis_monitor.py
  3. Format: uv run ruff format --check telegram_bot/bot.py telegram_bot/services/redis_monitor.py tests/unit/test_bot_scores.py tests/unit/services/test_redis_monitor.py
  4. MyPy: uv run mypy telegram_bot/bot.py telegram_bot/services/redis_monitor.py --ignore-missing-imports
  5. Unit tests (ТОЛЬКО затронутые файлы): uv run pytest tests/unit/test_bot_scores.py tests/unit/services/test_redis_monitor.py -v
  6. Если есть lint/format ошибки — пофикси и закоммить: style: lint fixes for memory observability #159

ТЕСТЫ (строго по файлам):
- ТОЛЬКО целевые тест-файлы: test_bot_scores.py + test_redis_monitor.py
- НЕ запускай tests/unit/ целиком — это долго и не нужно
- Маппинг:
  telegram_bot/bot.py -> tests/unit/test_bot_scores.py
  telegram_bot/services/redis_monitor.py -> tests/unit/services/test_redis_monitor.py

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Если ВСЁ чисто и тесты проходят — НЕ коммить, просто сообщи результат.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-verify.log (APPEND):
[START] timestamp Task 6: lint + full test suite
[DONE] timestamp Task 6: result
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:Claude" "W-VERIFY COMPLETE — проверь logs/worker-verify.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:Claude" Enter
ВАЖНО: Используй ИМЯ окна "Claude", НЕ индекс. Индекс сдвигается при kill-window.
