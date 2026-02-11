W-T5: Integration Verification (Sprint 1 final gate)

SKILLS (обязательно вызови):
1. /verification-before-completion — обязательно перед финальным отчётом

Работай из /repo. Ветка fix/issue120-umbrella.
Выполняй ТОЛЬКО Task 5 из плана: /repo/docs/plans/2026-02-10-sprint1-latency-correctness.md

КОНТЕКСТ:
- Tasks 1-4 выполнены: commits acf3361, 1e5fa50, e4862d3, 69c2863
- Нужно убедиться что все изменения работают вместе

ЗАДАЧИ (выполняй по порядку):
1. Step 1: Full unit test suite
   uv run pytest tests/unit/ -n auto -q
   Ожидание: no new failures
2. Step 2: Integration tests
   uv run pytest tests/integration/test_graph_paths.py -v
   Ожидание: all 6 path tests PASS
3. Step 3: Lint + types
   uv run ruff check src telegram_bot tests services --output-format=concise
   uv run mypy src telegram_bot --ignore-missing-imports
   Ожидание: clean для изменённых модулей
4. Если есть failures — запиши в лог что именно упало и почему, НЕ пытайся фиксить

НЕ делай коммитов. НЕ меняй файлы. Только запускай проверки и логируй результаты.

ЛОГИРОВАНИЕ в /repo/logs/worker-t5-verify.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /repo/logs/worker-t5-verify.log
echo "[DONE] $(date +%H:%M:%S) Step N: result summary" >> /repo/logs/worker-t5-verify.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker T5 finished" >> /repo/logs/worker-t5-verify.log

WEBHOOK (после завершения ВСЕХ проверок):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-T5 COMPLETE — проверь logs/worker-t5-verify.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
