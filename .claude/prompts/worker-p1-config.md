W-P1-CONFIG: Fix 3 P1/P2 issues (#116, #118, #119)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-10-issue120-umbrella-execution.md
Работай из /home/user/projects/rag-fresh. Ты на ветке fix/issue120-umbrella.

ЗАДАЧИ (выполняй по порядку):

Task 4.1 (#116): Sync rewrite_max_tokens default
- Прочитай план Task 4.1 целиком
- Прочитай telegram_bot/graph/config.py
- Замени fallback "200" на "64" в from_env() (строка ~70)
- Проверь grep: rewrite_max_tokens должен быть 64 и в dataclass default и в env fallback
- Запусти: uv run pytest tests/ -k "config" -q
- Lint: uv run ruff check telegram_bot/graph/config.py --output-format=concise
- Commit: git add telegram_bot/graph/config.py && commit с "Closes #116"

Task 4.2 (#118): test_redis_cache legacy imports
- Прочитай план Task 4.2 целиком
- Прочитай tests/integration/test_redis_cache.py
- Добавь pytestmark = pytest.mark.legacy_api маркер
- Обнови docstring, добавь import pytest
- Проверь: uv run pytest tests/integration/test_redis_cache.py --collect-only
- Проверь: uv run pytest tests/integration/test_redis_cache.py -m "not legacy_api" --collect-only (0 collected)
- Lint: uv run ruff check tests/integration/test_redis_cache.py --output-format=concise
- Commit: git add tests/integration/test_redis_cache.py && commit с "Closes #118"

Task 4.4 (#119): mypy duplicate module name
- Прочитай план Task 4.4 целиком
- Сначала попробуй воспроизвести: uv run mypy src telegram_bot --ignore-missing-imports
- Если duplicate НЕ воспроизводится в основном контуре — значит fix не нужен для CI
- Попробуй: uv run mypy services --ignore-missing-imports (тут должна быть ошибка)
- Фикс: минимально-инвазивный, не трогай основной CI path если не нужно
- Проверь оба контура после фикса
- Commit: git add измененные файлы && commit с "Closes #119"

ТЕСТЫ (строго по файлам):
- Task 4.1: uv run pytest tests/ -k "config" -q
- Task 4.2: uv run pytest tests/integration/test_redis_cache.py --collect-only
- Task 4.4: uv run mypy src telegram_bot --ignore-missing-imports
- НЕ запускай tests/ целиком

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query)
- Exa: web_search_exa(query) или get_code_context_exa(query)

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Каждый commit message через HEREDOC формат.

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-p1-config.log (APPEND):
Каждое действие логируй через: echo "[TAG] $(date +%H:%M:%S) message" >> /home/user/projects/rag-fresh/logs/worker-p1-config.log
Теги: [START], [DONE], [ERROR], [COMPLETE]
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker P1-CONFIG finished" >> /home/user/projects/rag-fresh/logs/worker-p1-config.log

После завершения ВСЕХ задач выполни ДВЕ bash команды:
1. TMUX="" tmux send-keys -t "claude:1" "W-P1-CONFIG COMPLETE — проверь logs/worker-p1-config.log"
2. sleep 0.5
3. TMUX="" tmux send-keys -t "claude:1" Enter
