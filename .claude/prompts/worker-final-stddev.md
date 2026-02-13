W-FINAL: Add stddev column to report + update docs (Tasks 5+6 from plan)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans -- для пошагового выполнения задач
2. /requesting-code-review -- code review ПОСЛЕ каждой таски, ПЕРЕД коммитом
3. /verification-before-completion -- финальная проверка

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-12-validation-thresholds-plan.md
Работай из /home/user/projects/rag-fresh. Ветка: fix/168-validation-thresholds (уже в ней). Tasks 1-4 уже завершены.

ЗАДАЧИ:

== Task 5: Add stddev column to Go/No-Go report ==

1. Прочитай scripts/validate_traces.py -- найди функцию compute_aggregates (ищи "def compute_aggregates"). Также прочитай evaluate_go_no_go и generate_report чтобы понять текущий формат.

2. Добавь тест в tests/unit/test_validate_aggregates.py:
   def test_aggregates_include_stddev(self):
       -- Создай 3+ результата с разной latency (2000, 3000, 4000)
       -- Вызови compute_aggregates
       -- Проверь "latency_stddev" in cold
       -- Проверь значение stddev (для [2000, 3000, 4000] np.std ~ 816.5)
   Используй существующий _make_result helper с phase="cold" и разной latency.

3. Запусти тест, убедись что FAIL (latency_stddev не в aggregates)

4. В scripts/validate_traces.py, в compute_aggregates:
   -- Добавь после существующих percentile computations: phase_agg["latency_stddev"] = float(np.std(latencies)) if len(latencies) > 1 else 0.0
   -- ВАЖНО: найди где latencies массив формируется и добавь stddev рядом с p50/p95/mean/max

5. Запусти тест, убедись что PASS

6. В evaluate_go_no_go: добавь "stddev" ключ в criteria dict для latency-based критериев:
   cold_stddev = cold.get("latency_stddev", 0)
   -- Для cold_p50_lt_5s, cold_p90_lt_8s: "stddev": f"+/-{cold_stddev:.0f} ms" if cold_stddev else "---"
   cache_stddev = cache.get("latency_stddev", 0)
   -- Для cache_hit_p50_lt_1500ms: "stddev": f"+/-{cache_stddev:.0f} ms" if cache_stddev else "---"
   -- Для generate_p50_lt_2s: "stddev": "---" (no per-node stddev yet)
   -- Для остальных критериев: "stddev": "---"

7. В generate_report, обнови Go/No-Go таблицу (в секции "if go_no_go:"):
   -- Заголовок: "| # | Criterion | Target | Actual | Stddev | Status |"
   -- Разделитель: "|---|-----------|--------|--------|--------|--------|"
   -- Каждая строка: stddev = c.get("stddev", "---") и добавь его в строку таблицы

8. В generate_report, в phase summary table (секция "for phase_name, phase_label"):
   -- Добавь строку после latency max: if "latency_stddev" in agg: lines.append(f"| latency stddev | {agg['latency_stddev']:.0f} ms |")

9. Запусти ВСЕ тесты: uv run pytest tests/unit/test_validate_aggregates.py tests/baseline/test_thresholds_schema.py -v
   Ожидай: ALL PASS

10. Lint: uv run ruff check scripts/validate_traces.py tests/unit/test_validate_aggregates.py && uv run ruff format --check scripts/validate_traces.py tests/unit/test_validate_aggregates.py

11. Коммит: feat(validation): add stddev column to Go/No-Go report #168

== Task 6: Update docs ==

1. Прочитай .claude/rules/observability.md

2. В секции "## Thresholds (regression detection)":
   -- Измени строку LLM calls: "+5%" -> "+15%"
   -- Добавь: "Config: tests/baseline/thresholds.yaml (includes go_no_go section for validate_traces.py)"

3. В секции "## Trace Validation (#110, #143)":
   -- Удали упоминание "Reference trace c2b95d86 --- anomalous (5213s), not reproducible."
   -- Добавь: "Go/No-Go thresholds are config-driven via tests/baseline/thresholds.yaml go_no_go section (#168)."

4. Коммит: docs(observability): update thresholds docs for #168

ТЕСТЫ:
- scripts/validate_traces.py -> tests/unit/test_validate_aggregates.py
- tests/baseline/thresholds.yaml -> tests/baseline/test_thresholds_schema.py
- Финальная проверка: uv run pytest tests/unit/test_validate_aggregates.py tests/baseline/test_thresholds_schema.py -v

ПРАВИЛА:
1. git commit -- ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. _format_go_no_go_status уже существует -- используй его (не создавай заново).
4. evaluate_go_no_go уже принимает thresholds параметр -- не ломай его.
5. compute_aggregates уже вычисляет p50/p90/p95/mean/max -- просто добавь stddev рядом.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-final-stddev.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N Step M: description" >> /home/user/projects/rag-fresh/logs/worker-final-stddev.log
echo "[DONE] $(date +%H:%M:%S) Task N Step M: result" >> /home/user/projects/rag-fresh/logs/worker-final-stddev.log
echo "[COMPLETE] $(date +%H:%M:%S) W-FINAL finished" >> /home/user/projects/rag-fresh/logs/worker-final-stddev.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-FINAL COMPLETE -- проверь logs/worker-final-stddev.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
