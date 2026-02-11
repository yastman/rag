W-GATE: Re-baseline + Go/No-Go gate (#101) + close parent (#105)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-11-re-baseline-plan.md
Работай из /home/user/projects/rag-fresh

КОНТЕКСТ: Все 8 implementation issues (#121, #122, #91, #123, #108, #106, #103, #124) завершены.
Нужно выполнить Gate 1: проверить что всё работает вместе, зафиксировать baseline.

ЗАДАЧИ:

Шаг 1: Preflight — проверить что MUST issues закрыты
- gh issue list --milestone "Gate: Re-Baseline" --state open --json number,title
- Если открыты — закрыть через gh issue close с комментарием

Шаг 2: НЕ делать docker rebuild (у нас нет Docker в dev, только код + тесты)
- Вместо этого: полный прогон тестов для проверки что все коммиты совместимы
  uv run pytest tests/unit/ -n auto --timeout=30
  uv run pytest tests/integration/test_graph_paths.py -v
  uv run ruff check telegram_bot/ tests/ src/
- Если тесты падают — фикси merge conflicts и запускай снова

Шаг 3: Добавить Go/No-Go автоматику в scripts/validate_traces.py (по плану)
- Функция evaluate_go_no_go(aggregates, results) -> dict[str, bool]
- Проверки: cold_p50 < 5000, cold_p90 < 8000, cache_hit_p50 < 1500, etc.
- Вывод в report: таблица с чекбоксами

Шаг 4: Добавить orphan trace check (по плану)
- Функция check_orphan_traces(results) -> float

Шаг 5: Коммит изменений validate_traces.py

Шаг 6: Закрыть issues
- gh issue close 121 --comment "Fixed in bugfix sprint #131"
- gh issue close 122 --comment "Fixed in bugfix sprint #131"
- gh issue close 91 --comment "Fixed in bugfix sprint #131"
- gh issue close 123 --comment "Fixed in bugfix sprint #131"
- gh issue close 108 --comment "Fixed in bugfix sprint #131"
- gh issue close 106 --comment "Phase A done in bugfix sprint #131"
- gh issue close 103 --comment "Fixed in bugfix sprint #131"
- gh issue close 124 --comment "Fixed in bugfix sprint #131"
- gh issue close 101 --comment "Gate 1: all MUST issues resolved. Validation script updated. Re-baseline pending Docker deploy."
- gh issue close 105 --comment "All child issues resolved (#107, #108, #109). Gate 1 passed."

ТЕСТЫ:
  uv run pytest tests/unit/ -n auto --timeout=30
  uv run pytest tests/integration/test_graph_paths.py -v
  uv run ruff check telegram_bot/ tests/ src/

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Коммит: feat(baseline): add Go/No-Go automation to validate_traces (#101)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-gate.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /home/user/projects/rag-fresh/logs/worker-gate.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /home/user/projects/rag-fresh/logs/worker-gate.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-gate.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:3" "W-GATE COMPLETE — проверь logs/worker-gate.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:3" Enter
