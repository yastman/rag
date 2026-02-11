W-BGE: BGE-M3 cold start fix Phase A (#106)

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения задач
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-11-bge-cold-start-plan.md

Работай из /home/user/projects/rag-fresh
ТОЛЬКО Phase A (Quick Fix). Phase B (ONNX) НЕ делать.

ЗАДАЧИ (выполняй по плану Phase A):

Task A1: Добавить startup warmup через FastAPI lifespan в services/bge-m3-api/app.py
- Заменить создание app на lifespan-based pattern
- В lifespan: get_model() + dummy encode для прогрева
- Залогировать время загрузки

Task A2: Добавить QUERY_MAX_LENGTH=256 в services/bge-m3-api/config.py
- MAX_LENGTH=2048 для документов остаётся
- QUERY_MAX_LENGTH=256 — новое, для коротких запросов

Task A3: Добавить keep-warm encode в telegram_bot/preflight.py
- После GET /health добавить POST /encode/dense с dummy текстом
- timeout=120.0 для первого запроса

Task A4: Обновить /health endpoint — добавить warmed_up field
- Глобальный _warmed_up = False, set True после lifespan warmup
- /health возвращает warmed_up: true/false

Task A5: НЕ делать (baseline метрики — ручной шаг)

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName, query) затем query-docs(libraryId, query) для FastAPI lifespan API
- Exa: get_code_context_exa(query) для примеров FastAPI lifespan warmup

ТЕСТЫ (строго по файлам):
- services/bge-m3-api/ — нет unit тестов в проекте. Проверь lint:
  uv run ruff check services/bge-m3-api/ && uv run ruff format --check services/bge-m3-api/
- telegram_bot/preflight.py -> tests/unit/test_preflight.py
  uv run pytest tests/unit/test_preflight.py -v
- Если test_preflight.py не существует, проверь через ruff + mypy
- НЕ запускай tests/ целиком

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы. НЕ git add -A.
2. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
3. Коммиты: perf(bge-m3): add startup warmup via lifespan (#106) и perf(bot): add keep-warm encode to preflight (#106)

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-bge.log (APPEND):
Используй Bash tool: echo "[START] $(date +%H:%M:%S) Task: description" >> /home/user/projects/rag-fresh/logs/worker-bge.log
[DONE] timestamp Task: result
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:2" "W-BGE COMPLETE — проверь logs/worker-bge.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:2" Enter
