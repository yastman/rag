W-COLL: Baseline collector — per-trace metrics computation (#167)

SKILLS (обязательно вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения задач
2. /requesting-code-review — code review ПОСЛЕ завершения ВСЕХ задач, ПЕРЕД финальным коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion — финальная проверка перед коммитом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-12-baseline-ci-isolation-plan.md
Работай из /home/user/projects/rag-fresh
Ветка: fix/167-baseline-ci-isolation (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ЗАДАЧИ (выполняй строго по порядку):
- Task 1: Test — collect_session_metrics happy path (test_collector.py)
- Task 2: Test — None guards on observations (test_collector.py)
- Task 3: Test — tag-based filtering (test_collector.py)
- Task 4: Implement — SessionMetrics dataclass + collect_session_metrics (collector.py)
- Task 8: Wire manager.py — deprecate create_snapshot
- Task 12: Cleanup — remove deprecated aggregate methods (collector.py, test_collector.py)

Прочитай план ЦЕЛИКОМ перед началом работы. Каждый таск содержит точный код и команды.

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id("langfuse", "Python SDK trace list observations API") затем query-docs для актуальной документации Langfuse API shapes
- Exa: get_code_context_exa("Langfuse Python SDK v3 api.trace.list api.observations.list response format") для примеров

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО тесты для файлов которые ты изменил:
  uv run pytest tests/baseline/test_collector.py -v
  uv run pytest tests/baseline/test_manager.py -v
- НЕ запускай tests/ целиком, НЕ запускай tests/unit/ целиком
- Маппинг source -> test:
  tests/baseline/collector.py -> tests/baseline/test_collector.py
  tests/baseline/manager.py -> tests/baseline/test_manager.py
- Используй --lf для перезапуска только упавших
- Финальная проверка: uv run pytest tests/baseline/test_collector.py tests/baseline/test_manager.py tests/baseline/test_collector_infra.py -v

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. ЗАПРЕЩЕНО git add -A или git add .
2. ПЕРЕД коммитом: git diff --cached --stat — убедись что ТОЛЬКО нужные файлы
3. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите
4. НЕ трогай файлы cli.py, test_cli.py, ci.yml, Makefile — это зона Worker B
5. ruff check + ruff format перед каждым коммитом: uv run ruff check tests/baseline/collector.py tests/baseline/test_collector.py tests/baseline/manager.py --fix && uv run ruff format tests/baseline/collector.py tests/baseline/test_collector.py tests/baseline/manager.py

ВАЖНО для import pytest:
- В test файлах добавь import pytest (нужен для pytest.approx, pytest.raises)
- SessionMetrics и _percentile будут в collector.py

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-baseline-collector.log (APPEND):
В начале каждого таска: echo "[START] $(date +%H:%M:%S) Task N: description" >> /home/user/projects/rag-fresh/logs/worker-baseline-collector.log
В конце каждого: echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /home/user/projects/rag-fresh/logs/worker-baseline-collector.log
После всех задач: echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-baseline-collector.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-COLL COMPLETE — проверь logs/worker-baseline-collector.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Используй ИМЯ окна "ORCH", НЕ индекс. Индекс сдвигается при kill-window.
