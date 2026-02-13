W-REPORT: Remove reference trace + improve SKIP formatting (Tasks 3+4 from plan)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans -- для пошагового выполнения задач
2. /requesting-code-review -- code review ПОСЛЕ каждой таски, ПЕРЕД коммитом. Делай review САМОСТОЯТЕЛЬНО (git diff, стиль, логика, тесты)
3. /verification-before-completion -- финальная проверка

ПЛАН: /repo/docs/plans/2026-02-12-validation-thresholds-plan.md
Работай из /repo. Ветка: fix/168-validation-thresholds (уже создана, ты в ней).

ЗАДАЧИ (выполняй по порядку):

== Task 3: Remove hardcoded reference trace ==

1. Прочитай scripts/validate_traces.py целиком (или ключевые секции): строка 48 (REFERENCE_TRACE_ID), функцию fetch_reference_trace_metrics (~строки 754-790), generate_report (~строки 950-984 reference section), run_validation (~строка 1186 вызов fetch_reference_trace_metrics).

2. Добавь тест в tests/unit/test_validate_aggregates.py:
   def test_report_no_reference_trace_section(tmp_path):
       Создай ValidationRun и вызови generate_report с reference_metrics=None. Проверь что "c2b95d86" НЕ в тексте отчета и "Reference Trace Comparison" НЕ в тексте.
   ВАЖНО: generate_report может иметь reference_metrics как параметр -- посмотри текущую сигнатуру.

3. Удали из scripts/validate_traces.py:
   a) Строка 48: REFERENCE_TRACE_ID = "c2b95d86..." -- удали целиком
   b) Функцию fetch_reference_trace_metrics целиком (~строки 754-790)
   c) В generate_report: удали строку с "Reference trace:" в хедере (lines.append с REFERENCE_TRACE_ID)
   d) В generate_report: удали весь блок "if reference_metrics:" (Reference Trace Comparison section, ~строки 966-984)
   e) В generate_report: удали параметр reference_metrics из сигнатуры функции
   f) В run_validation: удали вызов fetch_reference_trace_metrics() и передачу reference_metrics в generate_report

4. Проверь что нет broken imports: uv run python -c "from scripts.validate_traces import evaluate_go_no_go, generate_report"

5. Запусти тесты: uv run pytest tests/unit/test_validate_aggregates.py -v

6. Коммит: fix(validation): remove dead reference trace c2b95d86 #168

== Task 4: Improve SKIP explanation in report ==

1. Добавь тесты в tests/unit/test_validate_aggregates.py:
   class TestGoNoGoReportFormat:
       def test_skipped_criterion_shows_reason(self):
           criterion = {"target": "< 1000 ms", "actual": "N/A (n=2, need >= 3)", "passed": True, "skipped": True}
           from scripts.validate_traces import _format_go_no_go_status
           status = _format_go_no_go_status(criterion)
           assert "SKIPPED" in status
           assert "n=" in status or "insufficient" in status.lower()
       def test_pass_criterion_format(self):
           entry = {"target": "< 5000 ms", "actual": "3200 ms", "passed": True}
           from scripts.validate_traces import _format_go_no_go_status
           assert "PASS" in _format_go_no_go_status(entry)
       def test_fail_criterion_format(self):
           entry = {"target": "< 5000 ms", "actual": "6100 ms", "passed": False}
           from scripts.validate_traces import _format_go_no_go_status
           assert "FAIL" in _format_go_no_go_status(entry)

2. Запусти тесты, убедись что FAIL (_format_go_no_go_status не существует)

3. В scripts/validate_traces.py, добавь helper-функцию ПЕРЕД generate_report:
   def _format_go_no_go_status(criterion: dict[str, Any]) -> str:
       if criterion.get("skipped"):
           return f"[-] SKIPPED ({criterion['actual']})"
       elif criterion["passed"]:
           return "[x] PASS"
       else:
           return "[ ] **FAIL**"

4. В generate_report, замени inline форматирование (строки ~1062-1068) на вызов helper:
   for i, (name, c) in enumerate(go_no_go.items(), 1):
       status = _format_go_no_go_status(c)
       lines.append(f"| {i} | {name} | {c['target']} | {c['actual']} | {status} |")

5. Запусти тесты: uv run pytest tests/unit/test_validate_aggregates.py -v -k "GoNoGoReportFormat or report_no_reference"

6. Коммит: fix(validation): explicit SKIPPED reason in Go/No-Go report #168

ТЕСТЫ (строго по файлам):
- scripts/validate_traces.py -> tests/unit/test_validate_aggregates.py
- Запускай ТОЛЬКО этот файл. НЕ запускай tests/ целиком.
- Финальная проверка: uv run pytest tests/unit/test_validate_aggregates.py -v && uv run ruff check scripts/validate_traces.py tests/unit/test_validate_aggregates.py && uv run ruff format --check scripts/validate_traces.py tests/unit/test_validate_aggregates.py

ПРАВИЛА:
1. git commit -- ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. НЕ трогай evaluate_go_no_go (хардкод-значения, сигнатуру, thresholds) -- их рефакторит W-CONFIG.
4. НЕ добавляй stddev -- это делает другой воркер (Task 5).
5. НЕ трогай thresholds.yaml -- его обновляет W-CONFIG.
6. ВАЖНО: при удалении reference_metrics из generate_report, проверь ВСЕ вызовы generate_report в файле и обнови их.

ЛОГИРОВАНИЕ в /repo/logs/worker-report-cleanup.log (APPEND):
Перед каждым шагом: echo "[START] $(date +%H:%M:%S) Task N Step M: description" >> /repo/logs/worker-report-cleanup.log
После каждого шага: echo "[DONE] $(date +%H:%M:%S) Task N Step M: result" >> /repo/logs/worker-report-cleanup.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) W-REPORT finished" >> /repo/logs/worker-report-cleanup.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-REPORT COMPLETE -- проверь logs/worker-report-cleanup.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Три ОТДЕЛЬНЫХ вызова Bash tool. НЕ объединяй в одну команду. Sleep 1 секунда.
ВАЖНО: Используй ИМЯ окна "claude:ORCH", НЕ индекс.
