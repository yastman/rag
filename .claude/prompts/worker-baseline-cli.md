W-CLI: Baseline CLI — rewrite compare command with session isolation (#167)

SKILLS (обязательно вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения задач
2. /requesting-code-review — code review ПОСЛЕ завершения ВСЕХ задач, ПЕРЕД финальным коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion — финальная проверка перед коммитом

ПЛАН: /repo/docs/plans/2026-02-12-baseline-ci-isolation-plan.md
Работай из /repo
Ветка: fix/167-baseline-ci-isolation (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ЗАДАЧИ (выполняй строго по порядку):
- Task 5: Test — CLI bootstrap SKIP (test_cli.py) — МОЖНО НАЧАТЬ СРАЗУ (тесты мокают collector)
- Task 6: Test — CLI new flags + JSON output (test_cli.py) — МОЖНО НАЧАТЬ СРАЗУ
- Task 7: Implement — Rewrite compare command (cli.py)
  ВАЖНО: Task 7 импортирует SessionMetrics из collector.py. Перед началом Task 7 проверь:
  uv run python -c "from tests.baseline.collector import SessionMetrics; print('OK')"
  Если ошибка — Worker A ещё не закончил Task 4. Подожди 30 сек и проверь снова (макс 5 попыток).
- Task 9: Remove .current_baseline + rewrite set-baseline (cli.py, test_cli.py, .gitignore)
- Task 10: Update CI workflow (ci.yml)
- Task 11: Update Makefile

Прочитай план ЦЕЛИКОМ перед началом работы. Каждый таск содержит точный код и команды.

ИЗМЕНЕНИЕ В ПЛАНЕ (user правка): --output теперь REQUIRED (не optional). В compare функции:
  @click.option("--output", required=True, help="Path to write JSON report artifact (always written)")
  def compare(baseline_tag: str, current_session: str, thresholds: str, output: str):
Убери все if output: проверки — output всегда есть.

Также _metrics_to_snapshot принимает session_id как отдельный аргумент:
  def _metrics_to_snapshot(metrics, *, tag: str, session_id: str, ts) -> BaselineSnapshot:
Для baseline: session_id=f"baseline:{baseline_tag}"
Для current: session_id=current_session

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id("langfuse", "Python SDK trace update tags API") для документации Langfuse trace update API
- Exa: get_code_context_exa("GitHub Actions upload-artifact v4 2026") для актуального синтаксиса actions

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО тесты для файлов которые ты изменил:
  uv run pytest tests/baseline/test_cli.py -v
- НЕ запускай tests/ целиком
- Маппинг source -> test:
  tests/baseline/cli.py -> tests/baseline/test_cli.py
- Используй --lf для перезапуска только упавших
- Финальная проверка: uv run pytest tests/baseline/test_cli.py -v

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. ЗАПРЕЩЕНО git add -A или git add .
2. ПЕРЕД коммитом: git diff --cached --stat — убедись что ТОЛЬКО нужные файлы
3. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите
4. НЕ трогай файлы collector.py, test_collector.py, manager.py — это зона Worker A
5. ruff check + ruff format перед каждым коммитом: uv run ruff check tests/baseline/cli.py tests/baseline/test_cli.py --fix && uv run ruff format tests/baseline/cli.py tests/baseline/test_cli.py
6. Для ci.yml и Makefile: проверяй YAML валидность: python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"

ВАЖНО для test_cli.py:
- Старые тесты TestBaselineCLI для --baseline/--current флагов нужно УДАЛИТЬ или обновить
- Новые классы: TestCompareBootstrap, TestCompareNewFlags (из плана)
- Оставь test_cli_help, test_compare_help (обнови ожидаемые флаги)
- import json, from pathlib import Path — добавить в imports

ЛОГИРОВАНИЕ в /repo/logs/worker-baseline-cli.log (APPEND):
В начале каждого таска: echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-baseline-cli.log
В конце каждого: echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-baseline-cli.log
После всех задач: echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-baseline-cli.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-CLI COMPLETE — проверь logs/worker-baseline-cli.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Используй ИМЯ окна "ORCH", НЕ индекс. Индекс сдвигается при kill-window.
