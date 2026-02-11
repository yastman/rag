W-GUARD: Rewrite stop-guard (#108)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-11-rewrite-guard-plan.md
Работай из /home/user/projects/rag-fresh

ЗАДАЧИ (выполняй по плану):

Task 1: Добавить state field и config
- telegram_bot/graph/state.py: добавить score_improved: bool в RAGState, "score_improved": True в make_initial_state
- telegram_bot/graph/config.py: добавить score_improvement_delta: float = 0.001 + from_env
- Написать тест test_initial_state_has_score_improved

Task 2: Обновить grade_node — вычислять score delta
- telegram_bot/graph/nodes/grade.py: добавить delta = top_score - prev_confidence, score_improved = delta >= config.score_improvement_delta or prev_confidence == 0.0
- Написать 5 тестов TestGradeNodeScoreImproved

Task 3: Обновить route_grade — проверять score_improved
- telegram_bot/graph/edges.py: добавить and state.get("score_improved", True) в условие rewrite
- Написать 3 теста: test_score_not_improved_stops_rewrite, test_score_improved_allows_rewrite, test_score_improved_default_true

Task 4: Интеграционный тест — test_path_rewrite_stopped_by_score_guard
- tests/integration/test_graph_paths.py: новый тест

Task 5: Lint + полные тесты

ТЕСТЫ (строго по файлам):
  uv run pytest tests/unit/graph/test_edges.py tests/unit/graph/test_agentic_nodes.py -v
  uv run pytest tests/integration/test_graph_paths.py -v
- Маппинг:
  telegram_bot/graph/state.py -> tests/unit/graph/test_edges.py (test_initial_state)
  telegram_bot/graph/nodes/grade.py -> tests/unit/graph/test_agentic_nodes.py
  telegram_bot/graph/edges.py -> tests/unit/graph/test_edges.py
  tests/integration/test_graph_paths.py -> сам файл
- ВАЖНО: state.py также меняется в #124 (llm_* поля). Твоя область — score_improved field. Добавляй его ПЕРЕД последним полем TypedDict.
- ВАЖНО: test_graph_paths.py также меняется в #123 (traced_pipeline обёртка). Твоя область — НОВЫЙ тест test_path_rewrite_stopped_by_score_guard. НЕ трогай существующие тесты.

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Три коммита по плану: feat(graph): add score_improved state + config (#108), feat(graph): add score delta to grade_node (#108), feat(graph): add score_improved guard to route_grade (#108)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-guard.log (APPEND):
echo "[START] $(date +%H:%M:%S) Task N: description" >> /home/user/projects/rag-fresh/logs/worker-guard.log
echo "[DONE] $(date +%H:%M:%S) Task N: result" >> /home/user/projects/rag-fresh/logs/worker-guard.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker finished" >> /home/user/projects/rag-fresh/logs/worker-guard.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:2" "W-GUARD COMPLETE — проверь logs/worker-guard.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:2" Enter
