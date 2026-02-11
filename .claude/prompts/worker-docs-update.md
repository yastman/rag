W-DOCS: Update CLAUDE.md and rules files after Sprint 1

Работай из /repo. Ветка fix/issue120-umbrella.

КОНТЕКСТ Sprint 1 (4 коммита уже в ветке):
1. perf(embeddings): BGEM3HybridEmbeddings — single /encode/hybrid call вместо раздельных dense+sparse. Shared httpx.AsyncClient с connection pooling. Класс в telegram_bot/integrations/embeddings.py.
2. fix(observability): latency_total_ms теперь wall-time (time.perf_counter в handle_query), а не sum(latency_stages).
3. fix(grade): relevance_threshold_rrf = 0.005 (env RELEVANCE_THRESHOLD_RRF). Старый RELEVANCE_THRESHOLD=0.3 удалён. Configurable через GraphConfig.
4. feat(observability): embeddings_cache_hit, search_cache_hit, confidence_score — реальные значения в Langfuse scores вместо hardcoded 0.0.

ЗАДАЧИ:

1. Прочитай текущие файлы:
   - /repo/CLAUDE.md
   - /repo/.claude/rules/features/embeddings.md
   - /repo/.claude/rules/features/search-retrieval.md
   - /repo/.claude/rules/features/caching.md
   - /repo/.claude/rules/observability.md
   - /repo/.claude/rules/services.md

2. Обнови CLAUDE.md (ТОЧЕЧНО, не переписывай целиком):
   - В таблице Settings добавь RELEVANCE_THRESHOLD_RRF=0.005 (если нет)
   - В Architecture секции: упомяни hybrid embed (1 call) если ещё не отражено
   - Убедись что файл < 200 строк
   - НЕ добавляй лишнего, только отражение Sprint 1 изменений

3. Обнови .claude/rules/features/embeddings.md:
   - Добавь BGEM3HybridEmbeddings класс и /encode/hybrid endpoint
   - Connection pooling через shared httpx.AsyncClient
   - aembed_hybrid() возвращает (dense, sparse) tuple
   - Убери/пометь старый pattern раздельных dense+sparse вызовов как deprecated

4. Обнови .claude/rules/observability.md:
   - latency_total_ms: wall-time (pipeline_wall_ms), не sum(stages)
   - Новые real scores: embeddings_cache_hit, search_cache_hit, confidence_score
   - Обнови таблицу 12 scores если она есть

5. Обнови .claude/rules/features/search-retrieval.md (если нужно):
   - relevance_threshold_rrf = 0.005 для RRF scores
   - RRF score scale: 1/(k+rank), k=60

6. Каждый rules file < 500 строк

ПРАВИЛА CLAUDE-MD-WRITER:
- CLAUDE.md < 200 строк (golden rule)
- Rules files < 500 строк
- Критические правила наверх
- Pointers over copies (ссылки на файлы, не дублирование)
- НЕ добавляй code style rules (это для ruff/mypy)
- Только точечные правки, НЕ переписывай файлы целиком

ТЕСТЫ: НЕ нужны (только документация)

git commit — ТОЛЬКО изменённые .md файлы:
- НЕ git add -A
- Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
- Формат: docs: update CLAUDE.md and rules for Sprint 1 changes

ЛОГИРОВАНИЕ в /repo/logs/worker-docs-update.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /repo/logs/worker-docs-update.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /repo/logs/worker-docs-update.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker DOCS finished" >> /repo/logs/worker-docs-update.log

WEBHOOK (после завершения):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-DOCS COMPLETE — проверь logs/worker-docs-update.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
