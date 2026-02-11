W-P91: Написать план реализации для issue #91 (Audit remediation CI + smoke tests)

Ты — воркер, пишущий ПЛАН реализации (НЕ код).

Шаги:
1. Прочитай issue: gh issue view 91 --json title,body,labels,milestone
2. Прочитай исходные файлы (список ниже)
3. Напиши план в docs/plans/2026-02-11-audit-remediation-plan.md
4. Залогируй результат

Рабочая директория: /home/user/projects/rag-fresh

ФАЙЛЫ ДЛЯ ЧТЕНИЯ:
- .github/workflows/ci.yml (CI pipeline config)
- tests/smoke/test_zoo_smoke.py (legacy smoke tests, if exists)
- telegram_bot/integrations/cache.py (CacheLayerManager — migrated API)
- Makefile (test targets)
- pyproject.toml (dependencies, test config, pytest markers)
- tests/conftest.py (shared fixtures)

MCP TOOLS: не требуется (CI config, локальный код)

ФОРМАТ ПЛАНА:
- Заголовок: "# Audit Remediation: CI + Smoke Tests — Implementation Plan"
- Goal, Issue link
- Текущее состояние: что broken в CI, какие smoke tests устарели
- Шаги реализации: 2-5 минут каждый
- Test Strategy, Acceptance Criteria, Effort Estimate
НЕ используй markdown code blocks (тройные бэктики) — используй отступы 4 пробела.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-plan-91.log (APPEND):
echo "[START] $(date +%H:%M:%S) Issue #91" >> logs/worker-plan-91.log
echo "[DONE] $(date +%H:%M:%S) Issue #91: plan written" >> logs/worker-plan-91.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> logs/worker-plan-91.log

WEBHOOK (после завершения — ТРИ ОТДЕЛЬНЫХ вызова Bash tool):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-P91 COMPLETE — проверь logs/worker-plan-91.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter

ПРАВИЛА:
1. НЕ пиши код, НЕ делай коммиты — только план-документ
2. НЕ используй тройные бэктики в план-файле
3. Каждый шаг = конкретный файл + номер строки + что менять
