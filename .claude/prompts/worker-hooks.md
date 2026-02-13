W-HOOKS: SDK hooks spike — checkpoint tracing design (Issue #162)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения
2. /verification-before-completion — финальная проверка

MCP TOOLS (используй для исследования — это КЛЮЧЕВОЕ для этой задачи):
- Context7: resolve-library-id(libraryName="langgraph", query="AsyncRedisSaver checkpoint hooks") затем query-docs
- Context7: resolve-library-id(libraryName="langgraph-checkpoint-redis", query="checkpoint save load instrumentation") затем query-docs
- Exa: web_search_exa("langgraph checkpoint redis instrumentation tracing 2026")
- Exa: get_code_context_exa("langgraph AsyncRedisSaver AsyncShallowRedisSaver checkpoint hooks custom subclass")
- Exa: web_search_exa("langgraph-checkpoint-redis source code AsyncRedisSaver load save methods 2026")
- Exa: web_search_exa("langfuse observe decorator redis checkpoint tracing overhead measurement")

КОНТЕКСТ:
Issue #162: SDK-level InstrumentedAsyncRedisSaver hooks for checkpoint tracing.
Deferred from #159 — нет callback hooks в SDK для checkpoint load/save.
Текущий подход (#159): graph.ainvoke() wall-time минус сумма pipeline stages = proxy для checkpointer overhead.

3 опции для исследования:
1. Upstream PR к langgraph-checkpoint-redis добавляющий load/save hooks
2. AsyncShallowRedisSaver как более лёгкая альтернатива
3. Custom subclass с @observe wrappers (риск: tight coupling к internals)

РАБОЧАЯ ДИРЕКТОРИЯ: /home/USER/projects/rag-w/hooks
ВЕТКА: chore/parallel-backlog/hooks-162 (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ФАЗА 1 — ГЛУБОКОЕ ИССЛЕДОВАНИЕ (ОСНОВНАЯ ФАЗА):
1. Исследуй через Context7: LangGraph checkpoint architecture, AsyncRedisSaver API
2. Исследуй через Context7: есть ли уже hooks/events в SDK для checkpoint operations
3. Исследуй через Exa: upstream issues/PRs в langgraph-checkpoint-redis для instrumentation
4. Исследуй через Exa: примеры custom checkpoint savers с observability
5. Исследуй через Exa: AsyncShallowRedisSaver — что это, когда использовать, overhead
6. Прочитай текущий код: telegram_bot/graph/graph_builder.py (как создаётся checkpointer)
7. Прочитай proxy подход: telegram_bot/observability.py (как сейчас измеряется overhead)
8. Напиши план исследования в docs/plans/2026-02-12-sdk-hooks-spike-plan.md

ФАЗА 2 — DESIGN DOC:
1. Напиши design doc: docs/plans/2026-02-12-sdk-hooks-spike-design.md
   Структура:
   - Problem Statement: зачем нужны per-operation метрики
   - Current State: proxy approach из #159
   - Option 1: Upstream PR
     - Feasibility (SDK architecture)
     - Timeline estimate
     - Pros/Cons
   - Option 2: AsyncShallowRedisSaver
     - What it does differently
     - Performance implications
     - Migration path
   - Option 3: Custom subclass + @observe
     - Implementation sketch (pseudocode, НЕ markdown code blocks — plain text)
     - Coupling risks
     - Maintenance burden
   - Recommendation: какой вариант лучше и почему
   - Next Steps: конкретные action items
2. Коммит design doc

ПРАВИЛА:
1. Работай ТОЛЬКО в /home/USER/projects/rag-w/hooks
2. НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки
3. Это RESEARCH + DESIGN задача. Основной код НЕ менять.
4. git commit — ТОЛЬКО docs/. ЗАПРЕЩЕНО git add -A
5. ПЕРЕД коммитом: git diff --cached --stat
6. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

ЛОГИРОВАНИЕ в /repo/logs/worker-hooks.log (APPEND):
Формат: echo "[START/DONE] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-hooks.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker hooks finished" >> /repo/logs/worker-hooks.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-HOOKS COMPLETE — проверь logs/worker-hooks.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
