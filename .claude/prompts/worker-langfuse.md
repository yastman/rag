W-LANGFUSE: Langfuse dashboard design for latency breakdown (Issue #147)

SKILLS (вызови В ЭТОМ ПОРЯДКЕ):
1. /executing-plans — для пошагового выполнения
2. /verification-before-completion — финальная проверка

MCP TOOLS (используй для исследования):
- Context7: resolve-library-id(libraryName="langfuse", query="dashboards alerts scores configuration") затем query-docs
- Exa: web_search_exa("langfuse v3 dashboard configuration scores alerts 2026 best practices")
- Exa: get_code_context_exa("langfuse dashboard API create score alerts p95 latency monitoring")
- Exa: web_search_exa("LLM observability latency breakdown TTFT queue decode dashboard design 2026")

КОНТЕКСТ:
Issue #147: track slow-thinking latency breakdown (queue, TTFT, decode).
Уже реализовано в runtime (scores пишутся в трейсы):
- llm_queue_ms, llm_ttft_ms, llm_decode_ms, llm_tps, llm_timeout, streaming_enabled

Осталось:
1. Dashboards/alerts в Langfuse: llm_queue_ms_p95, llm_ttft_ms_p95, llm_decode_ms_p95, % llm_timeout
2. Evidence — скриншоты/отчёт что дашборды работают
3. Документация: как классифицировать slow cases (queue-bound vs model-bound)

Связанное: #144 (TTFT gate pending), текущий gate проверяет generate_p50_lt_2s.

РАБОЧАЯ ДИРЕКТОРИЯ: /home/USER/projects/rag-w/langfuse
ВЕТКА: chore/parallel-backlog/langfuse-147 (уже checkout). НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки.

ФАЗА 1 — ИССЛЕДОВАНИЕ И ПЛАН:
1. Прочитай текущие scores: telegram_bot/observability.py (найди latency-related scores)
2. Прочитай validate_traces: scripts/validate_traces.py (как scores используются)
3. Исследуй через MCP (Context7): Langfuse v3 dashboard API, score aggregation
4. Исследуй через Exa: LLM latency monitoring dashboards best practices 2026
5. Исследуй через Exa: queue-bound vs model-bound classification patterns
6. Напиши план в docs/plans/2026-02-12-langfuse-dashboards-plan.md

ФАЗА 2 — ВЫПОЛНЕНИЕ:
1. Напиши design doc: docs/plans/2026-02-12-langfuse-dashboards-design.md
   Включи:
   - Dashboard layout: какие panels, какие метрики
   - Alert rules: thresholds для p95 queue/ttft/decode
   - Classification guide: queue-bound vs model-bound decision tree
   - Langfuse API calls или UI steps для создания dashboards
2. Если Langfuse имеет API для dashboard creation — напиши скрипт scripts/setup_langfuse_dashboards.py
3. Напиши runbook: docs/runbooks/latency-investigation.md
   - Как найти slow trace
   - Как определить bottleneck (queue vs ttft vs decode)
   - Escalation criteria
4. Коммит все документы

ПРАВИЛА:
1. Работай ТОЛЬКО в /home/USER/projects/rag-w/langfuse
2. НЕ ПЕРЕКЛЮЧАЙСЯ на другие ветки
3. git commit — ТОЛЬКО конкретные файлы. ЗАПРЕЩЕНО git add -A
4. ПЕРЕД коммитом: git diff --cached --stat
5. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
6. Это DESIGN + DOCS задача. Основной код НЕ менять.

ЛОГИРОВАНИЕ в /repo/logs/worker-langfuse.log (APPEND):
Формат: echo "[START/DONE] $(date +%H:%M:%S) Task N: description" >> /repo/logs/worker-langfuse.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker langfuse finished" >> /repo/logs/worker-langfuse.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:ORCH" "W-LANGFUSE COMPLETE — проверь logs/worker-langfuse.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:ORCH" Enter
