W-GEN: Generate Token Cap (Task 1)

ПЛАН: /repo/docs/plans/2026-02-10-latency-phase2-impl.md
Работай из /repo
Ветка: fix/issue-91-ci-smoke-remediation (уже checkout)

ЗАДАЧА: Task 1 — Generate Token Cap (generate_max_tokens config knob)

Выполняй шаги СТРОГО по плану (Steps 1-7):

1. Добавь тест test_generate_max_tokens_default в tests/unit/graph/test_config.py
2. Добавь поле generate_max_tokens: int = 2048 в GraphConfig (telegram_bot/graph/config.py)
3. Добавь from_env() маппинг GENERATE_MAX_TOKENS
4. Добавь тест test_respects_generate_max_tokens в tests/unit/graph/test_generate_node.py
5. Замени max_tokens=config.llm_max_tokens на max_tokens=config.generate_max_tokens в generate_node
6. Добавь GENERATE_MAX_TOKENS env var в docker-compose.dev.yml (после BGE_M3_TIMEOUT строки в секции bot)
7. Запусти тесты: uv run pytest tests/unit/graph/test_config.py tests/unit/graph/test_generate_node.py -v
8. Commit с сообщением из плана

ПРАВИЛА:
1. ТЕСТЫ — только свои модули (test_config.py, test_generate_node.py). НЕ запускай весь tests/unit/
2. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
3. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
4. После каждого Edit используй grep для проверки что изменение применилось.
5. Используй uv run pytest (не просто pytest).

MCP TOOLS:
- ПЕРЕД реализацией внешних SDK/API используй MCP Context7 (resolve-library-id, query-docs) для актуальной документации
- Для поиска решений и best practices используй MCP Exa (web_search_exa, get_code_context_exa)

ВЕРИФИКАЦИЯ перед коммитом:
- uv run pytest tests/unit/graph/test_config.py tests/unit/graph/test_generate_node.py -v
- uv run ruff check telegram_bot/graph/config.py telegram_bot/graph/nodes/generate.py --fix
- uv run ruff format telegram_bot/graph/config.py telegram_bot/graph/nodes/generate.py

ЛОГИРОВАНИЕ в /repo/logs/worker-gen-cap.log (APPEND):
[START] timestamp Task 1: Generate Token Cap
[DONE] timestamp Task 1: result summary
[COMPLETE] timestamp Worker finished

После завершения ВСЕХ задач выполни ДВЕ bash команды:
1. TMUX="" tmux send-keys -t "claude:6" "W-GEN COMPLETE — проверь logs/worker-gen-cap.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:6" Enter
