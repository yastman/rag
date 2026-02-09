W-BASELINE: Запусти unit тесты и сохрани полный отчёт о фейлах

Работай из /repo

Шаги:

1. Запусти: uv run pytest tests/unit/ -q --tb=short 2>&1 | tee /repo/logs/unit-baseline.txt
2. Добавь в конец файла: echo "[COMPLETE]" >> /repo/logs/unit-baseline.txt
3. Проанализируй результат и создай файл /repo/logs/unit-failures-analysis.txt с:
   - Общее количество passed/failed/error
   - Список ВСЕХ FAILED тестов сгруппированных по файлу
   - Список ВСЕХ ERROR тестов сгруппированных по причине
   - Для каждой группы: причина фейла и предлагаемый фикс
   - Категории: UNIT_FIX (реальный баг в тесте), SKIP (requires docker/service), FLAKY (timing)

Формат файла:

UNIT TEST BASELINE ANALYSIS
============================
Total: X passed, Y failed, Z errors
Date: timestamp

FAILED TESTS BY FILE:
  tests/unit/test_xxx.py:
    test_name — причина — категория (UNIT_FIX/SKIP/FLAKY)
    ...

ERROR TESTS:
  причина: список тестов

RECOMMENDED FIX GROUPS (для параллельных воркеров):
  Group A (файлы): описание что фиксить
  Group B (файлы): описание что фиксить
  Group C (файлы): описание что фиксить

НЕ фикси тесты, только анализ!

Логирование в /repo/logs/worker-test-baseline.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook — после завершения:
TMUX="" tmux send-keys -t "claude:1" "W-BASELINE COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
