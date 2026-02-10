W-SKIP: Early Termination — Skip Rerank (Task 3)

ПЛАН: /repo/docs/plans/2026-02-10-latency-phase2-impl.md
Работай из /repo
Ветка: fix/issue-91-ci-smoke-remediation (уже checkout)

ЗАДАЧА: Task 3 — Early Termination: Skip Rerank When Grade Confidence High

Выполняй шаги СТРОГО по плану (Steps 1-9):

1. Добавь тест test_high_confidence_skips_rerank в tests/unit/graph/test_edges.py
2. Добавь grade_confidence: float в RAGState (telegram_bot/graph/state.py)
3. Добавь "grade_confidence": 0.0 в make_initial_state
4. Добавь skip_rerank_threshold: float = 0.85 в GraphConfig (telegram_bot/graph/config.py)
5. Добавь from_env() маппинг SKIP_RERANK_THRESHOLD
6. Обнови grade_node (telegram_bot/graph/nodes/grade.py) — добавь grade_confidence: top_score в return dict
7. Обнови route_grade (telegram_bot/graph/edges.py):
   - Если documents_relevant И confidence >= threshold: return "generate" (skip rerank)
   - Иначе если documents_relevant: return "rerank"
   - Используй _get_skip_rerank_threshold() функцию (os.getenv)
8. Добавь тест test_relevant_low_confidence_routes_to_rerank
9. Запусти тесты: uv run pytest tests/unit/graph/ -v --timeout=30

ВАЖНО:
- route_grade СНАЧАЛА проверяет documents_relevant, потом confidence
- Если confidence >= threshold: "generate" (пропустить rerank)
- Если confidence < threshold: "rerank" (стандартный путь)
- threshold берётся из env var SKIP_RERANK_THRESHOLD (default 0.85)
- _get_skip_rerank_threshold() — отдельная функция (import os, os.getenv)

ФАЙЛЫ которые ты редактируешь:
- telegram_bot/graph/edges.py
- telegram_bot/graph/state.py
- telegram_bot/graph/config.py (ОСТОРОЖНО: Task 1 тоже меняет этот файл. Добавляй skip_rerank_threshold ПОСЛЕ max_rewrite_attempts. Не удаляй generate_max_tokens если он уже есть)
- telegram_bot/graph/nodes/grade.py
- tests/unit/graph/test_edges.py
- tests/unit/graph/test_state.py

ПРАВИЛА:
1. ТЕСТЫ — только tests/unit/graph/ . НЕ запускай весь tests/
2. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
3. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
4. После каждого Edit используй grep для проверки что изменение применилось.
5. Используй uv run pytest (не просто pytest).
6. Если видишь что config.py уже изменён другим воркером (generate_max_tokens), НЕ удаляй его изменения. Добавляй свои поля рядом.

MCP TOOLS:
- ПЕРЕД реализацией внешних SDK/API используй MCP Context7 (resolve-library-id, query-docs) для актуальной документации
- Для поиска решений и best practices используй MCP Exa (web_search_exa, get_code_context_exa)

ВЕРИФИКАЦИЯ перед коммитом:
- uv run pytest tests/unit/graph/test_edges.py tests/unit/graph/test_state.py -v
- uv run ruff check telegram_bot/graph/edges.py telegram_bot/graph/nodes/grade.py telegram_bot/graph/state.py --fix
- uv run ruff format telegram_bot/graph/edges.py telegram_bot/graph/nodes/grade.py telegram_bot/graph/state.py

ЛОГИРОВАНИЕ в /repo/logs/worker-early-term.log (APPEND):
[START] timestamp Task 3: Early Termination
[DONE] timestamp Task 3: result summary
[COMPLETE] timestamp Worker finished

После завершения ВСЕХ задач выполни ДВЕ bash команды:
1. TMUX="" tmux send-keys -t "claude:6" "W-SKIP COMPLETE — проверь logs/worker-early-term.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:6" Enter
