# Test Coverage 80% — Design Plan

**Дата:** 2026-01-26
**Цель:** Достичь 80% покрытия тестами для `telegram_bot/services/`
**Текущее покрытие:** 57%
**Подход:** Качество (исправить все тесты, не skip'ать)

---

## Архитектура

```
┌─────────────────────────────────────────────────────────┐
│                    ОРКЕСТРАТОР                          │
│         docs/plans/2026-01-26-test-coverage-tasks.md    │
└─────────────────────┬───────────────────────────────────┘
                      │
        ┌─────────────┴─────────────┐
        ▼                           ▼
┌───────────────────┐     ┌───────────────────┐
│    WORKER 1       │     │    WORKER 2       │
│  Fix 22 failing   │     │  Write new tests  │
│     tests         │     │   +23% coverage   │
│                   │     │                   │
│  Track 1:         │     │  Track 2:         │
│  - filter_ext     │     │  - cache.py       │
│  - metrics_log    │     │  - user_context   │
│  - otel_setup     │     │  - qdrant.py      │
│  - evaluator      │     │  - query_router   │
│                   │     │  - cesc.py        │
└───────────────────┘     └───────────────────┘
```

**Принципы:**
- Воркеры работают с разными файлами — нет конфликтов
- Общий файл задач — синхронизация через чеклисты
- Без auto-approve — каждое действие требует подтверждения

---

## Файл задач

`docs/plans/2026-01-26-test-coverage-tasks.md`

- Track 1: 22 задачи (fix failing tests)
- Track 2: 31 задача (write new tests)
- Воркер берёт `[ ]`, после завершения ставит `[x]`

---

## Команды запуска

### Worker 1 — Fix Failing Tests

```bash
spawn-claude "Ты Worker 1. Файл задач: docs/plans/2026-01-26-test-coverage-tasks.md

Твоя задача: исправить failing теста в Track 1.

Алгоритм:
1. Прочитай файл задач, найди Track 1
2. Возьми первую незавершённую [ ] задачу
3. Запусти pytest для этого теста, пойми ошибку
4. Исправь код или тест (приоритет качества)
5. Убедись что тест проходит
6. Отметь [x] в файле задач, сделай git commit
7. Повтори пока все задачи Track 1 не будут [x]

Команда проверки: . venv/bin/activate && pytest tests/unit/ -q --tb=short
Не трогай файлы Track 2."
```

### Worker 2 — Write New Tests

```bash
spawn-claude "Ты Worker 2. Файл задач: docs/plans/2026-01-26-test-coverage-tasks.md

Твоя задача: написать тесты для достижения 80% покрытия в Track 2.

Алгоритм:
1. Прочитай файл задач, найди Track 2
2. Возьми первую незавершённую [ ] задачу (модуль)
3. Прочитай код модуля в telegram_bot/services/
4. Напиши тесты в tests/unit/test_<module>.py
5. Запусти pytest --cov для проверки покрытия
6. Отметь [x] в файле задач, сделай git commit
7. Повтори пока все задачи Track 2 не будут [x]

Команда проверки: . venv/bin/activate && pytest tests/unit/ --cov=telegram_bot/services --cov-report=term
Не трогай файлы Track 1."
```

---

## Критерии успеха

| Критерий | Команда | Результат |
|----------|---------|-----------|
| 0 failing | `pytest tests/unit/ -q` | `0 failed` |
| 80% coverage | `pytest --cov=telegram_bot/services --cov-fail-under=80` | `PASSED` |
| Все задачи | `grep "\[x\]" ...tasks.md \| wc -l` | 53 |

---

## Финальная проверка

```bash
. venv/bin/activate && pytest tests/unit/ --cov=telegram_bot/services --cov-report=term --cov-fail-under=80 -q
```
