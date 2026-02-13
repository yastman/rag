W-CHAOS: Fix chaos LLM fallback tests (Issue #164, PR #180)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения
2. /requesting-code-review — code review ПОСЛЕ завершения, ПЕРЕД коммитом. Делай review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику, тесты
3. /verification-before-completion — финальная проверка перед коммитом

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName="pytest-httpx", query="mock async openai retries") затем query-docs для актуальной документации
- Context7: resolve-library-id(libraryName="openai python sdk", query="AsyncOpenAI retry behavior testing") затем query-docs
- Exa: get_code_context_exa("pytest-httpx mock AsyncOpenAI retry responses 2026") для примеров
- Exa: web_search_exa("openai python sdk v1 retry configuration testing best practices 2026")

КОНТЕКСТ:
Issue #164: Все 16 chaos тестов в tests/chaos/test_llm_fallback.py падают с TypeError.
Тесты написаны под старый LLMService API (api_key=..., client=...).
Текущий LLMService имеет другой конструктор.
PR #180 уже создан на ветке fix/164-chaos-llm-api, но CI lint ПАДАЕТ.
3 теста в TestLowConfidenceFallback проходят (не используют LLMService напрямую).

РАБОЧАЯ ДИРЕКТОРИЯ: /home/user/projects/rag-w/chaos
ВЕТКА: chore/parallel-backlog/chaos-164 (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ФАЗА 1 — ИССЛЕДОВАНИЕ И ПЛАН:
1. Прочитай текущий LLMService: telegram_bot/services/llm_service.py (конструктор, методы)
2. Прочитай тесты: tests/chaos/test_llm_fallback.py (все 16 тестов)
3. Прочитай PR #180 diff: git diff main..origin/fix/164-chaos-llm-api -- tests/chaos/
4. Исследуй через MCP (Context7 + Exa): pytest-httpx patterns, AsyncOpenAI mocking, retry behavior
5. Напиши план в docs/plans/2026-02-12-chaos-tests-fix-plan.md

ФАЗА 2 — ВЫПОЛНЕНИЕ:
1. Обнови тесты чтобы использовать текущий LLMService API (смотри что сделано в PR #180 как reference)
2. Запусти ruff check: uv run ruff check tests/chaos/test_llm_fallback.py --fix
3. Запусти ruff format: uv run ruff format tests/chaos/test_llm_fallback.py
4. Запусти тесты: uv run pytest tests/chaos/test_llm_fallback.py -v
5. Если тесты падают — дебажь и фикси (используй --lf для перезапуска упавших)

ТЕСТЫ:
- tests/chaos/test_llm_fallback.py — ЕДИНСТВЕННЫЙ файл для тестов
- НЕ запускай другие тесты и директории
- Маппинг: telegram_bot/services/llm_service.py -> tests/chaos/test_llm_fallback.py

ПРАВИЛА:
1. Работай ТОЛЬКО в /home/user/projects/rag-w/chaos
2. НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки
3. git commit — ТОЛЬКО конкретные файлы. ЗАПРЕЩЕНО git add -A
4. ПЕРЕД коммитом: git diff --cached --stat — убедись что ТОЛЬКО нужные файлы
5. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-chaos.log (APPEND):
Формат: echo "[START/DONE] $(date +%H:%M:%S) Task N: description" >> /home/user/projects/rag-fresh/logs/worker-chaos.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker chaos finished" >> /home/user/projects/rag-fresh/logs/worker-chaos.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-CHAOS COMPLETE — проверь logs/worker-chaos.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
