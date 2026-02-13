W-DEPS: Migrate dev dependencies to [dependency-groups] (PEP 735) #169

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения
2. /requesting-code-review — code review ПОСЛЕ завершения, ПЕРЕД коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику
3. /verification-before-completion — финальная проверка перед коммитом

ПЛАН: /repo/docs/plans/2026-02-12-dev-setup-and-preflight-plan.md
Работай из /repo. Ветка: fix/dev-setup-and-preflight (текущая, уже checkout).

ЗАДАЧИ (выполняй Task 1 из плана):

1. В pyproject.toml: перенеси содержимое [project.optional-dependencies].dev в новую секцию [dependency-groups].dev
   - Удали dev = [...] из [project.optional-dependencies] (оставь docs, voice, e2e и другие extras)
   - Добавь [dependency-groups] секцию с тем же списком пакетов
   - Формат: dev = ["ruff>=0.6.0", ...] (список строк, PEP 735)

2. В Makefile строка 40: install-dev уже использует "uv sync" — это теперь ПРАВИЛЬНО (dev group ставится по дефолту)
   - Строка 45 install-all: замени "uv sync --all-extras" на "uv sync --all-extras --all-groups"

3. В .github/workflows/ci.yml: замени ВСЕ "uv sync --frozen --extra dev" на "uv sync --frozen" (строки 26, 53, 85)

4. Запусти: uv lock (пересоздать lockfile)

5. Проверь что pytest доступен: uv run pytest --version && uv run ruff --version && uv run mypy --version

6. Запусти тесты: uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v

MCP TOOLS (используй ПЕРЕД реализацией если нужна документация):
- Context7: resolve-library-id(libraryName="uv", query="dependency-groups PEP 735") затем query-docs для актуальной документации
- Exa: get_code_context_exa(query="uv dependency-groups pyproject.toml migration") для примеров

ТЕСТЫ:
- pyproject.toml, Makefile, ci.yml — конфигурационные файлы, тесты через верификацию команд
- Запусти: uv run pytest --version (должен вывести версию)
- Запусти: uv run pytest tests/unit/test_validate_queries.py tests/unit/test_validate_aggregates.py -v
- НЕ запускай tests/ целиком

ПРАВИЛА:
1. git commit — ТОЛЬКО ЯВНО перечисленные файлы: git add pyproject.toml uv.lock Makefile .github/workflows/ci.yml
2. ЗАПРЕЩЕНО: git add -A, git add ., git add --all. Только git add с КОНКРЕТНЫМИ именами файлов.
3. ПЕРЕД коммитом: запусти git diff --cached --stat и убедись что ТОЛЬКО 4 файла в staging (pyproject.toml, uv.lock, Makefile, .github/workflows/ci.yml). Если там другие файлы — git reset HEAD и добавь заново только нужные.
4. НЕ удаляй .venv
5. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в коммите
6. Сообщение коммита: fix(build): migrate dev deps to [dependency-groups] (PEP 735) #169

ЛОГИРОВАНИЕ в /repo/logs/worker-deps.log (APPEND):
Перенаправляй ключевые шаги:
[START] timestamp Task 1: migrate dev deps
[DONE] timestamp Task 1: result summary
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-DEPS COMPLETE — проверь logs/worker-deps.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
ВАЖНО: Три ОТДЕЛЬНЫХ вызова Bash tool. НЕ объединяй в одну команду.
