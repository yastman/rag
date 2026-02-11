W-FINAL: Finalize #110 — cache-hit n>=10 + close issue

Работай из /repo. Без остановок.

ЗАДАЧИ:

ЗАДАЧА 1: Увеличить cache-hit выборку до 10
В scripts/validate_queries.py функция get_cache_hit_queries:
- Изменить default count=5 на count=10
- Расширить выборку: easy[:4] + medium (добавить) + hard[:4], итого до 10
- Пример:
  easy = [q for q in cold_queries if q.difficulty == "easy"][:4]
  medium = [q for q in cold_queries if q.difficulty == "medium"][:3]
  hard = [q for q in cold_queries if q.difficulty == "hard"][:3]
  return (easy + medium + hard)[:count]

ЗАДАЧА 2: Update тесты
В tests/unit/test_validate_queries.py обновить test_cache_hit_queries_mix:
- assert len(cache) <= 10 (было 5)
Запусти: uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v

ЗАДАЧА 3: Lint + commit
uv run ruff check scripts/validate_queries.py
uv run ruff format scripts/validate_queries.py
git add scripts/validate_queries.py tests/unit/test_validate_queries.py
git commit -m "fix(validation): increase cache-hit sample to n>=10 (#110)"
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

ЗАДАЧА 4: Удалить старые отчёты и запустить чистый baseline
rm -f docs/reports/2026-02-10-validation-*.md docs/reports/2026-02-10-validation-*.json
uv run python scripts/validate_traces.py --collection gdrive_documents_bge --report

ЗАДАЧА 5: Показать результат
cat docs/reports/2026-02-10-validation-*.md

ЗАДАЧА 6: Закрыть issue #110
Создай комментарий в #110 через gh issue comment 110 с:
- Run ID
- Ссылка на отчёт (docs/reports/файл.md)
- 10-20 trace IDs из JSON файла (jq '.traces[:20].trace_id' docs/reports/*.json)
- Итоговая таблица cold/cache (p50/p95/mean/max, n)
- Node breakdown (p50)
- Вывод: "Reference anomaly c2b95d86 (5213s) NOT reproducible. Baseline established."
Затем: gh issue close 110

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
3. НЕ останавливайся.

ЛОГИРОВАНИЕ в /repo/logs/worker-110-final.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-110-final.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-110-final.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-110-final.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-FINAL COMPLETE — проверь logs/worker-110-final.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
