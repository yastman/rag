W-FINAL: Финальная верификация всего test suite

Работай из /home/user/projects/rag-fresh
GitHub Issue: #44 — Task 12: Final verification

Это ФИНАЛЬНАЯ проверка. Запусти ВСЕ тесты и собери отчёт.

Шаги:

1. Unit тесты (полный прогон):
   uv run pytest tests/unit/ -q --tb=short 2>&1 | tee /home/user/projects/rag-fresh/logs/final-unit.txt

2. Smoke тесты:
   uv run pytest tests/smoke/ -q --tb=short 2>&1 | tee /home/user/projects/rag-fresh/logs/final-smoke.txt

3. Integration тесты (если Docker up):
   uv run pytest tests/integration/ -q --tb=short 2>&1 | tee /home/user/projects/rag-fresh/logs/final-integration.txt

4. Chaos тесты:
   uv run pytest tests/chaos/ -q --tb=short 2>&1 | tee /home/user/projects/rag-fresh/logs/final-chaos.txt

5. Создай финальный отчёт /home/user/projects/rag-fresh/logs/final-verification-report.txt:

FINAL VERIFICATION REPORT
=========================
Date: timestamp

Unit:        X passed, Y failed, Z skipped
Smoke:       X passed, Y failed, Z skipped
Integration: X passed, Y failed, Z skipped
Chaos:       X passed, Y failed, Z skipped

TOTAL: X passed, Y failed

Если есть failures — список с причинами.

STATUS: PASS / FAIL

6. Проверь git log — все коммиты сессии на месте
7. Проверь git status — нет ли uncommitted changes

НЕ делай git commit.

Логирование в /home/user/projects/rag-fresh/logs/worker-final.log (APPEND):
[START] timestamp
[DONE] timestamp
[COMPLETE] timestamp

Webhook:
TMUX="" tmux send-keys -t "claude:1" "W-FINAL COMPLETE"
sleep 0.5
TMUX="" tmux send-keys -t "claude:1" Enter
