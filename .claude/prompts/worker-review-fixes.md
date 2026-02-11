W-REVIEW: Fix code review findings (skip_rerank + isinstance)

Работай из /repo. Ветка main.
Создай новую ветку: git checkout -b fix/review-sprint1-findings

ДВЕ ЗАДАЧИ:

ЗАДАЧА 1 — skip_rerank_threshold недостижим на RRF шкале
Файлы: telegram_bot/graph/config.py, telegram_bot/graph/nodes/grade.py, tests/unit/graph/test_agentic_nodes.py, tests/unit/graph/test_edges.py

Проблема: skip_rerank_threshold=0.85, но RRF scores = 1/(60+rank) ~ 0.01-0.02. Условие grade_confidence >= 0.85 никогда не сработает, skip_rerank = мёртвый код.

FIX: Рекалибровать skip_rerank_threshold для RRF шкалы.
- RRF top-1: 1/61 = 0.0164
- Порог для "high confidence" (top-3 scores close together): ~0.012
- Изменить default в config.py: skip_rerank_threshold = 0.012
- Env var SKIP_RERANK_THRESHOLD уже есть, просто поменять default
- Добавить тест в test_agentic_nodes.py: RRF score 0.016 с confidence > 0.012 -> skip_rerank=True
- Проверить test_edges.py — route_grade должен корректно роутить skip_rerank

ЗАДАЧА 2 — isinstance слишком жёсткий для hybrid detection
Файлы: telegram_bot/graph/nodes/cache.py, telegram_bot/graph/nodes/retrieve.py, tests/unit/graph/test_cache_nodes.py, tests/unit/graph/test_retrieve_node.py, tests/integration/test_graph_paths.py

Проблема: isinstance(embeddings, BGEM3HybridEmbeddings) ломается для адаптеров/обёрток которые тоже имеют aembed_hybrid.

FIX: Заменить isinstance на capability check с проверкой что это реальный coroutine:
  _has_hybrid = callable(getattr(embeddings, "aembed_hybrid", None)) and asyncio.iscoroutinefunction(embeddings.aembed_hybrid)
  if _has_hybrid:
Это решает и проблему MagicMock (iscoroutinefunction вернёт False) и проблему адаптеров.
Применить в ДВУХ местах: cache.py и retrieve.py.
Убрать import BGEM3HybridEmbeddings из обоих файлов если он больше не нужен.
Проверить что integration tests проходят (MagicMock не имеет coroutine).

ПОРЯДОК:
1. Прочитай все файлы из обеих задач
2. Задача 2 первая (capability check) — она меняет cache.py и retrieve.py
3. Запусти: uv run pytest tests/integration/test_graph_paths.py tests/unit/graph/test_cache_nodes.py tests/unit/graph/test_retrieve_node.py -v
4. Задача 1 (skip_rerank threshold) — config.py и grade.py
5. Запусти: uv run pytest tests/unit/graph/test_agentic_nodes.py tests/unit/graph/test_edges.py -v
6. Финальный прогон всех затронутых: uv run pytest tests/integration/test_graph_paths.py tests/unit/graph/ tests/unit/test_bot_handlers.py tests/unit/integrations/test_embeddings.py -v
7. Lint: uv run ruff check на изменённых файлах
8. Commit: fix(graph): recalibrate skip_rerank for RRF + capability-based hybrid detection

git commit ТОЛЬКО изменённые файлы. НЕ git add -A.
Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>

ЛОГИРОВАНИЕ в /repo/logs/worker-review-fixes.log (APPEND):
echo "[START] $(date +%H:%M:%S) Step N: desc" >> /repo/logs/worker-review-fixes.log
echo "[DONE] $(date +%H:%M:%S) Step N: result" >> /repo/logs/worker-review-fixes.log
echo "[COMPLETE] $(date +%H:%M:%S) Worker REVIEW finished" >> /repo/logs/worker-review-fixes.log

WEBHOOK после завершения — ТРИ ОТДЕЛЬНЫХ Bash вызова:
1: TMUX="" tmux send-keys -t "claude:1" "W-REVIEW COMPLETE — проверь logs/worker-review-fixes.log"
2: sleep 1
3: TMUX="" tmux send-keys -t "claude:1" Enter
