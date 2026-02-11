W-T1: BGEM3HybridEmbeddings + Connection Pooling

SKILLS (обязательно вызови):
1. /executing-plans — для пошагового выполнения
2. /verification-before-completion — после выполнения, перед финальным отчётом

ПЛАН: /home/user/projects/rag-fresh/docs/plans/2026-02-10-sprint1-latency-correctness.md
Работай из /home/user/projects/rag-fresh. Ветка fix/issue120-umbrella.
Выполняй ТОЛЬКО Task 1 из плана (секция "Task 1: BGEM3HybridEmbeddings + Connection Pooling").

КОНТЕКСТ:
- Сейчас два отдельных HTTP вызова: /encode/dense + /encode/sparse
- Нужен один вызов /encode/hybrid который возвращает и dense_vecs и lexical_weights
- Shared httpx.AsyncClient для connection pooling
- BGE-M3 API: /encode/hybrid returns dense_vecs (list of float lists) и lexical_weights (list of dicts)
- ВАЖНО: Task 2 и Task 3 УЖЕ выполнены и закоммичены. bot.py и config.py обновлены.
  Прочитай текущее состояние файлов ПЕРЕД редактированием.

ЗАДАЧИ (выполняй по порядку):
1. Прочитай ВСЕ файлы которые будешь менять: telegram_bot/integrations/embeddings.py, telegram_bot/graph/nodes/retrieve.py, telegram_bot/graph/nodes/cache.py, telegram_bot/graph/graph.py, telegram_bot/bot.py, telegram_bot/graph/config.py, tests/unit/integrations/test_embeddings.py, tests/unit/graph/test_retrieve_node.py, tests/unit/graph/test_cache_nodes.py, tests/unit/test_bot_handlers.py
2. Step 1: Напиши failing тесты TestBGEM3HybridEmbeddings в tests/unit/integrations/test_embeddings.py (как в плане)
3. Step 2: Запусти тест, убедись что FAIL (ImportError)
4. Step 3: Реализуй BGEM3HybridEmbeddings класс в telegram_bot/integrations/embeddings.py
5. Step 4: Запусти тесты embeddings, убедись PASS
6. Step 5: Обнови GraphConfig — добавь create_hybrid_embeddings() в config.py
7. Step 6: Обнови PropertyBot.__init__ в bot.py — используй BGEM3HybridEmbeddings
8. Step 6.1: Обнови PropertyBot.stop() в bot.py — добавь cleanup для shared clients
9. Step 7: Обнови retrieve_node — используй hybrid когда re-embedding после rewrite
10. Step 8: Обнови cache_check_node — используй hybrid для initial embedding
11. Step 9: Запусти все тесты затронутых модулей
12. Step 10: Lint + commit

MCP TOOLS (используй ПЕРЕД реализацией):
- Context7: resolve-library-id(libraryName="httpx", query="async client connection pooling") затем query-docs для актуальной документации httpx
- Exa: get_code_context_exa(query="httpx AsyncClient connection pooling shared instance") для примеров

ТЕСТЫ (строго по файлам):
- Запускай ТОЛЬКО эти файлы:
  uv run pytest tests/unit/integrations/test_embeddings.py tests/unit/graph/test_retrieve_node.py tests/unit/graph/test_cache_nodes.py tests/unit/test_bot_handlers.py -v
- НЕ запускай tests/ целиком
- Маппинг source -> test:
  telegram_bot/integrations/embeddings.py -> tests/unit/integrations/test_embeddings.py
  telegram_bot/graph/nodes/retrieve.py -> tests/unit/graph/test_retrieve_node.py
  telegram_bot/graph/nodes/cache.py -> tests/unit/graph/test_cache_nodes.py
  telegram_bot/bot.py -> tests/unit/test_bot_handlers.py
- Используй --lf для перезапуска упавших
- Финальная проверка: uv run ruff check затронутых файлов

ПРАВИЛА:
1. git commit — ТОЛЬКО конкретные файлы (см. план Step 10)
2. НЕ git add -A
3. Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com> в коммите
4. Формат коммита как в плане
5. ПРОЧИТАЙ текущее состояние файлов перед редактированием — Task 2 и Task 3 уже изменили bot.py и config.py

ЛОГИРОВАНИЕ в /home/user/projects/rag-fresh/logs/worker-t1-hybrid.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: description" >> /home/user/projects/rag-fresh/logs/worker-t1-hybrid.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /home/user/projects/rag-fresh/logs/worker-t1-hybrid.log
В конце: echo "[COMPLETE] $(date +%H:%M:%S) Worker T1 finished" >> /home/user/projects/rag-fresh/logs/worker-t1-hybrid.log

WEBHOOK (после завершения ВСЕХ задач):
Выполни РОВНО ТРИ ОТДЕЛЬНЫХ вызова Bash tool (НЕ объединяй через && или ;):
Вызов 1: TMUX="" tmux send-keys -t "claude:1" "W-T1 COMPLETE — проверь logs/worker-t1-hybrid.log"
Вызов 2: sleep 1
Вызов 3: TMUX="" tmux send-keys -t "claude:1" Enter
