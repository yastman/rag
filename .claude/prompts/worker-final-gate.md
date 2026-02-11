W-FINAL-GATE: Phase 5 Final Gate verification + post to #120

Работай из /home/user/projects/rag-fresh. Ветка fix/issue120-umbrella.

ЗАДАЧИ:

1. Запусти все target tests:
   uv run pytest tests/unit/test_redis_semantic_cache.py tests/unit/test_vectorizers.py -q
   uv run pytest tests/unit/test_bot_handlers.py -q
   uv run pytest tests/integration/test_graph_paths.py -q
   uv run pytest tests/unit/graph/test_generate_node.py -q
   uv run pytest tests/unit/test_qdrant_error_signal.py -q

2. Запусти full unit suite:
   uv run pytest tests/unit/ -n auto -q

3. Запусти lint + mypy:
   uv run ruff check src telegram_bot tests services --output-format=concise
   uv run mypy src telegram_bot --ignore-missing-imports

4. Запости результаты в #120 (используй gh issue comment):

gh issue comment 120 --body "$(cat <<'GATE_EOF'
## Final Gate Results

### All 8 Commits
- e09135c #115 cross-test pollution
- 95bd424 #112 bot handler tests
- a374946 #113 graph path mocks
- 888543e #114 streaming fallback
- fb8f5fa #116 rewrite_max_tokens
- 454c6e0 #118 redis cache legacy
- 6460c2e #117 qdrant error signal
- f5fc1fd #119 mypy duplicate module

### Test Results
(вставь вывод из шага 2)

### Lint/Types
(вставь вывод из шага 3)

### Status
All P0 + P1/P2 code fixes complete. Next: Local Validation (Phase 3) + Deep Audit (Phase 3.7).
GATE_EOF
)"

5. Если какой-то тест упал — НЕ постить "all green", а описать что именно упало.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-final-gate.log (APPEND):
echo "[TAG] $(date +%H:%M:%S) message" >> /home/user/projects/rag-fresh/logs/worker-final-gate.log
Теги: [START], [DONE], [ERROR], [COMPLETE]

После завершения выполни:
1. TMUX="" tmux send-keys -t "claude:1" "W-FINAL-GATE COMPLETE — проверь logs/worker-final-gate.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:1" Enter
