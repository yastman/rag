W-RERUN: Post-fix validation run to verify latency_total_ms + true cold

Работай из /repo. Без остановок.

КОНТЕКСТ:
Коммит a7f4d6c пофиксил два бага:
1. latency_total_ms = 0.0 (score писался до вычисления wall-time)
2. cold run = warm (не было flush кэшей)
Нужен новый прогон чтобы подтвердить фиксы в Langfuse traces.

ЗАДАЧИ:

ЗАДАЧА 1: Удалить старые отчёты
rm -f docs/reports/2026-02-10-validation-*.md docs/reports/2026-02-10-validation-*.json

ЗАДАЧА 2: Запустить валидацию
uv run python scripts/validate_traces.py --collection gdrive_documents_bge --report
Дождись завершения.

ЗАДАЧА 3: Проверить что фиксы работают
Из JSON отчёта проверь:
- latency_total_ms в scores НЕ равен 0.0 (jq первые 3 trace)
- В cold фазе search_cache_hit должен быть false/0 (не 100%)
Команда: jq '.traces[:3] | .[] | {phase, latency: .latency_wall_ms, scores_latency: .scores.latency_total_ms, search_cache: .state.search_cache_hit}' docs/reports/2026-02-10-validation-*.json

ЗАДАЧА 4: Показать итоговый отчёт
cat docs/reports/2026-02-10-validation-*.md

ЗАДАЧА 5: Добавить комментарий в issue #110
gh issue comment 110 с:
- Run ID
- Подтверждение: latency_total_ms != 0.0
- Подтверждение: cold search_cache_hit = 0% (true cold)
- Таблица cold/cache p50/p95
- 5 trace IDs из JSON

ЛОГИРОВАНИЕ в /repo/logs/worker-validate-rerun.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-validate-rerun.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /repo/logs/worker-validate-rerun.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /repo/logs/worker-validate-rerun.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-RERUN COMPLETE — проверь logs/worker-validate-rerun.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
