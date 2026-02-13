W-MYPY: Fix mypy errors + redisvl import gate (#191)

SKILLS (вызывай В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения задач
2. /requesting-code-review — code review ПОСЛЕ всех фиксов, ПЕРЕД коммитом. ВАЖНО: делай review САМОСТОЯТЕЛЬНО (без субагента) — просмотри git diff, проверь стиль, логику
3. /verification-before-completion — финальная проверка перед коммитом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-12-ci-green-sweep-design.md
Работай из /home/user/projects/rag-fresh
Ветка: fix/191-ci-green-sweep (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ЗАДАЧИ (выполняй по порядку):

Task 1: Fix mypy no-any-return in sip_setup.py (#181)
  Файл: src/voice/sip_setup.py
  Строка 38: result.sip_trunk_id возвращает Any (LiveKit SDK untyped).
  Фикс: добавь cast(str, result.sip_trunk_id). Импортируй cast из typing.
  Было:
    return trunk_id
  Стало:
    trunk_id = cast(str, result.sip_trunk_id)
    return trunk_id
  Добавь import cast в начало файла (from typing import cast, или добавь cast в существующий typing import).

Task 2: Fix mypy no-any-return + type-var in graph.py (#181)
  Файл: telegram_bot/graph/graph.py
  Строка 150: summarize_wrapper возвращает result типа Any.
  Фикс: замени "return result" на "return cast(dict[str, Any], result)"
  Добавь cast в imports (from typing import Any, cast или добавь cast в существующий).
  Строка 152: workflow.add_node("summarize", summarize_wrapper) — LangGraph type-var issue.
  Фикс: добавь комментарий type: ignore
  Было:
    workflow.add_node("summarize", summarize_wrapper)
  Стало:
    workflow.add_node("summarize", summarize_wrapper)  # type: ignore[type-var]

Task 3: Fix redisvl import gate in test_vectorizers.py (#183)
  Файл: tests/unit/test_vectorizers.py
  Строки 6-9: текущий guard проверяет "import redisvl" (top-level), но при запуске полного suite test_redis_semantic_cache.py может инжектить MagicMock в sys.modules.
  Фикс: заменить guard на проверку точного sub-import:
  Было:
    try:
        import redisvl  # noqa: F401
    except (ImportError, ModuleNotFoundError, ValueError):
        pytest.skip("redisvl not installed", allow_module_level=True)
  Стало:
    try:
        from redisvl.utils.vectorize import BaseVectorizer  # noqa: F401
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError):
        pytest.skip("redisvl.utils.vectorize not available", allow_module_level=True)

ТЕСТЫ (строго по файлам):
- После Task 1+2: uv run mypy src/voice/sip_setup.py telegram_bot/graph/graph.py --ignore-missing-imports --no-error-summary
- После Task 3: uv run pytest tests/unit/test_vectorizers.py -v
- Финальная проверка: uv run mypy src/ telegram_bot/ --ignore-missing-imports --no-error-summary (должно быть 0 ошибок)
- Маппинг:
  src/voice/sip_setup.py -> mypy check only (нет unit tests)
  telegram_bot/graph/graph.py -> mypy check only (тесты graph не затронуты)
  tests/unit/test_vectorizers.py -> uv run pytest tests/unit/test_vectorizers.py -v

ЗАПРЕЩЕНО: git add -A. ПЕРЕД коммитом: git diff --cached --stat — убедись что ТОЛЬКО нужные файлы.
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в каждом коммите.
Commit message: fix(ci): resolve mypy errors and harden redisvl import gate (#191)
Scope коммита: src/voice/sip_setup.py, telegram_bot/graph/graph.py, tests/unit/test_vectorizers.py

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-mypy.log (APPEND):
Каждое действие логируй в файл через >> (append). Формат:
[START] timestamp Task N: description
[DONE] timestamp Task N: result
[COMPLETE] timestamp Worker finished

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:Claude2" "W-MYPY COMPLETE — проверь logs/worker-mypy.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:Claude2" Enter
ВАЖНО: Используй ИМЯ окна "Claude2", НЕ индекс. Индекс сдвигается при kill-window.
